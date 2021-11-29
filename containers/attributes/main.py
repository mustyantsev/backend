import json
import logging
import os
import sys
from enum import Enum
from http.client import NO_CONTENT
from pprint import pprint
from typing import Optional, List, Annotated

import databases as databases
import sqlalchemy
from asyncpg import UniqueViolationError
from fastapi import Depends
from fastapi import FastAPI, Request, HTTPException
from fastapi import Security, status
from fastapi.openapi.utils import get_openapi
from fastapi.security import OAuth2AuthorizationCodeBearer
from fastapi.security import OpenIdConnect
from keycloak import KeycloakOpenID
from pydantic import BaseSettings, Field
from pydantic import Json
from pydantic import ValidationError, AnyUrl
from pydantic.main import BaseModel
from sqlalchemy import and_

logging.basicConfig(
    stream=sys.stdout, level=os.getenv("SERVER_LOG_LEVEL", logging.CRITICAL)
)
logger = logging.getLogger(__package__)

swagger_ui_init_oauth = {
    "usePkceWithAuthorizationCodeGrant": True,
    "clientId": os.getenv("OIDC_CLIENT_ID"),
    "realm": os.getenv("OIDC_REALM"),
    "appName": os.getenv("SERVER_PUBLIC_NAME"),
    "scopes": ["email"],
}


class Settings(BaseSettings):
    openapi_url: str = "/openapi.json"


settings = Settings()

app = FastAPI(
    debug=True,
    swagger_ui_init_oauth=swagger_ui_init_oauth,
    openapi_url=settings.openapi_url,
)

oauth2_scheme = OAuth2AuthorizationCodeBearer(
    # format f"{keycloak_url}realms/{realm}/protocol/openid-connect/auth"
    authorizationUrl=os.getenv("OIDC_AUTHORIZATION_URL", ""),
    # format f"{keycloak_url}realms/{realm}/protocol/openid-connect/token"
    tokenUrl=os.getenv("OIDC_TOKEN_URL", ""),
)

keycloak_openid = KeycloakOpenID(
    # trailing / is required
    server_url=os.getenv("OIDC_SERVER_URL"),
    client_id=os.getenv("OIDC_CLIENT_ID"),
    realm_name=os.getenv("OIDC_REALM"),
    client_secret_key=os.getenv("OIDC_CLIENT_SECRET"),
    verify=True,
)


async def get_idp_public_key():
    return (
        "-----BEGIN PUBLIC KEY-----\n"
        f"{keycloak_openid.public_key()}"
        "\n-----END PUBLIC KEY-----"
    )


async def get_auth(token: str = Security(oauth2_scheme)) -> Json:
    logger.debug(token)
    if logger.isEnabledFor(logging.DEBUG):
        pprint(vars(keycloak_openid))
        pprint(vars(keycloak_openid.connection))
    try:
        return keycloak_openid.decode_token(
            token,
            key=await get_idp_public_key(),
            options={"verify_signature": True, "verify_aud": True, "exp": True},
        )
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),  # "Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


# database
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DATABASE = os.getenv("POSTGRES_DATABASE")
POSTGRES_SCHEMA = os.getenv("POSTGRES_SCHEMA")

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}/{POSTGRES_DATABASE}"
database = databases.Database(DATABASE_URL)

metadata = sqlalchemy.MetaData(schema=POSTGRES_SCHEMA)

table_authority = sqlalchemy.Table(
    "attribute_namespace",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("name", sqlalchemy.VARCHAR),
)

table_attribute = sqlalchemy.Table(
    "attribute",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column(
        "namespace_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("attribute_namespace.id"),
    ),
    sqlalchemy.Column("state", sqlalchemy.VARCHAR),
    sqlalchemy.Column("rule", sqlalchemy.VARCHAR),
    sqlalchemy.Column("name", sqlalchemy.VARCHAR),
    sqlalchemy.Column("description", sqlalchemy.VARCHAR),
    sqlalchemy.Column("values", sqlalchemy.ARRAY(sqlalchemy.TEXT)),
)

engine = sqlalchemy.create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)


# middleware
@app.middleware("http")
async def add_response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# OpenAPI
tags_metadata = [
    {
        "name": "Attributes",
        "description": "Operations to view data attributes."
        + "TDF protocol supports ABAC (Attribute Based Access Control)."
        + "This allows TDF protocol to implement policy driven and highly scalable access control mechanism.",
    },
    {
        "name": "Authorities",
        "description": "Operations to view and create attribute authorities.",
    },
    {
        "name": "Attributes Definitions",
        "description": "Operations to manage the rules and metadata of attributes. ",
    },
]


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="openTDF",
        version="1.0.0",
        routes=app.routes,
        tags=tags_metadata,
    )
    openapi_schema["info"]["x-logo"] = {
        "url": "https://inxmad4bw31barrx17wec71c-wpengine.netdna-ssl.com/wp-content/uploads/2018/12/o_efa1e48d0db5ebc8-4.png"
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


class RuleEnum(str, Enum):
    hierarchy = "hierarchy"
    anyOf = "anyOf"
    allOf = "allOf"


class AuthorityUrl(AnyUrl):
    max_length = 2000


class AttributeDefinition(BaseModel):
    authority: AuthorityUrl
    name: Annotated[str, Field(max_length=2000, exclusiveMaximum=2000)]
    order: Annotated[
        List[str],
        Field(max_length=2000, exclusiveMaximum=2000),
    ]
    rule: RuleEnum
    state: Annotated[Optional[str], Field(max_length=64, exclusiveMaximum=64)]

    class Config:
        schema_extra = {
            "example": {
                "authority": "https://opentdf.io",
                "name": "IntellectualProperty",
                "rule": "hierarchy",
                "state": "published",
                "order": ["TradeSecret", "Proprietary", "BusinessSensitive", "Open"],
            }
        }


class AuthorityDefinition(BaseModel):
    authority: AuthorityUrl


@app.on_event("startup")
async def startup():
    await database.connect()


@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


@app.get("/", include_in_schema=False)
async def read_semver():
    return {"Hello": "World"}


class ProbeType(str, Enum):
    liveness = "liveness"
    readiness = "readiness"


@app.get("/healthz", status_code=NO_CONTENT, include_in_schema=False)
async def read_liveness(probe: ProbeType = ProbeType.liveness):
    if probe == ProbeType.readiness:
        await database.execute("SELECT 1")


oidc_scheme = OpenIdConnect(
    openIdConnectUrl=os.getenv("OIDC_CONFIGURATION_URL", ""), auto_error=False
)


#
# Attributes
#


@app.get("/attributes", tags=["Attributes"], response_model=List[AnyUrl])
async def read_attributes():
    error = None
    authorities = await read_authorities()
    query = table_attribute.select()
    result = await database.fetch_all(query)
    attributes: List[AnyUrl] = []
    for row in result:
        for value in row.get("order"):
            try:
                attributes.append(
                    AnyUrl(
                        scheme=f"{authorities[0]}",
                        host=f"{authorities[row.get(table_attribute.c.namespace_id) - 1]}",
                        url=f"{authorities[row.get(table_attribute.c.namespace_id) - 1]}/attr/{row.get(table_attribute.c.name)}/value/{value}",
                    )
                )
            except ValidationError as e:
                logging.error(e)
                error = e
    if error and not attributes:
        raise HTTPException(
            status_code=422, detail=f"attribute error: {str(error)}"
        ) from error
    return attributes


#
# Attributes Definitions
#


@app.get(
    "/definitions/attributes",
    tags=["Attributes Definitions"],
    response_model=List[AttributeDefinition],
    dependencies=[Depends(get_auth)],
)
async def read_attributes_definitions():
    query = table_attribute.select()
    result = await database.fetch_all(query)
    attributes: List[AttributeDefinition] = []
    for row in result:
        try:
            attributes.append(
                AttributeDefinition(
                    authority=row.get(table_attribute.c.namespace_id),
                    name=row.get(table_attribute.c.name),
                    order=row.get("order"),
                    rule=row.get(table_attribute.c.rule),
                    state=row.get(table_attribute.c.state),
                )
            )
        except ValidationError as e:
            logging.error(e)
    return attributes


@app.post(
    "/definitions/attributes",
    tags=["Attributes Definitions"],
    response_model=AttributeDefinition,
    dependencies=[Depends(get_auth)],
)
async def create_attributes_definitions(request: AttributeDefinition):
    # lookup
    query = table_authority.select().where(table_authority.c.name == request.authority)
    result = await database.fetch_one(query)
    if result:
        if request.rule == RuleEnum.hierarchy:
            is_duplicated = check_duplicates(request.order)
            if is_duplicated:
                raise HTTPException(
                    status_code=400, detail="Duplicated items when Rule is Hierarchy"
                )
        namespace_id = result.get(table_authority.c.id)
        # insert
        query = table_attribute.insert().values(
            name=request.name,
            namespace_id=namespace_id,
            order=request.order,
            state=request.state,
            rule=request.rule,
        )
        try:
            await database.execute(query)
        except UniqueViolationError as e:
            raise HTTPException(status_code=400, detail=f"duplicate: {str(e)}") from e
    else:
        raise HTTPException(status_code=400, detail=f"namespace not found")
    return request


@app.put(
    "/definitions/attributes",
    tags=["Attributes Definitions"],
    response_model=AttributeDefinition,
    dependencies=[Depends(get_auth)],
)
async def update_attribute(request: AttributeDefinition):
    # update
    query = table_authority.select().where(table_authority.c.name == request.authority)
    result = await database.fetch_one(query)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Record not found"
        )

    if request.rule == RuleEnum.hierarchy:
        is_duplicated = check_duplicates(request.order)
        if is_duplicated:
            raise HTTPException(
                status_code=400, detail="Duplicated items when Rule is Hierarchy"
            )

    query = table_attribute.update().values(
        values=request.order,
    )

    await database.execute(query)
    return request


@app.delete(
    "/definitions/attributes",
    tags=["Attributes Definitions"],
    response_model=None,
    dependencies=[Depends(get_auth)],
)
async def delete_attributes_definitions(request: AttributeDefinition):
    statement = table_attribute.delete().where(
        and_(
            table_attribute.c.authority == request.authority,
            table_attribute.c.name == request.name,
            table_attribute.c.rule == request.rule,
            table_attribute.c.order == request.order,
        )
    )
    await database.execute(statement)
    return NO_CONTENT


#
# Authorities
#


@app.get("/authorities", tags=["Authorities"], dependencies=[Depends(get_auth)])
async def read_authorities():
    query = table_authority.select()
    result = await database.fetch_all(query)
    authorities = []
    for row in result:
        authorities.append(f"{row.get(table_authority.c.name)}")
    return authorities


@app.post("/authorities", tags=["Authorities"])  # , dependencies=[Depends(get_auth)])
async def create_authorities(request: AuthorityDefinition):
    # insert
    query = table_authority.insert().values(name=request.authority)
    try:
        await database.execute(query)
    except UniqueViolationError as e:
        raise HTTPException(status_code=400, detail=f"duplicate: {str(e)}") from e
    # select all
    query = table_authority.select()
    result = await database.fetch_all(query)
    namespaces = []
    for row in result:
        namespaces.append(f"{row.get(table_authority.c.name)}")
    return namespaces


# Check for duplicated items when rule is Hierarchy
def check_duplicates(hierarchy_list):
    if len(hierarchy_list) == len(set(hierarchy_list)):
        return False
    else:
        return True


if __name__ == "__main__":
    print(json.dumps(app.openapi()), file=sys.stdout)