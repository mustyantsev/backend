import os
import json
import logging
import yaml
from keycloak import KeycloakAdmin

URL_ADMIN_AUTHENTICATOR_EXECUTION_CONFIG = (
    "admin/realms/{realm-name}/authentication/executions/{flow-id}/config"
)
# We need to do this manually because KeycloakAdmin expects a 204 response and sometimes we get a valid 202.  :/
URL_ADMIN_EXECUTION_FLOW = (
    "admin/realms/{realm-name}/authentication/flows/{flow-alias}/executions"
)

URL_ADMIN_EXECUTIONS_EXECUTION = (
    "admin/realms/{realm-name}/authentication/flows/{flow-alias}/executions/execution"
)

logging.basicConfig()
logger = logging.getLogger("keycloak_bootstrap")
logger.setLevel(logging.DEBUG)

# These are the *only two URLs* anything should ever need:

# 1. The URL stuff outside the cluster will use to resolve keycloak or other external services (public, browser and non-browser clients)
# 2. The URL stuff inside the cluster will use to resolve keycloak (private, non-browser clients)
otdf_frontend_url = os.getenv("OPENTDF_EXTERNAL_URL", "http://localhost:65432").rstrip("/")
kc_internal_url = os.getenv("KEYCLOAK_INTERNAL_URL", "http://keycloak-http").rstrip("/")
pki_browser = os.getenv("ENABLE_PKI_BROWSER", "")
pki_direct = os.getenv("ENABLE_PKI_DIRECTGRANT", "")

def check_matched(pattern, allData):
    filtered_item = [
        d for d in allData if all((k in d and d[k] == v) for k, v in pattern.items())
    ]
    if filtered_item is not None:
        return filtered_item
    return []

def createPreloadedUsersInRealm(keycloak_admin, preloaded_users):
    for item in preloaded_users:
        try:
            new_user = keycloak_admin.create_user(
                {
                    "username": item["username"],
                    "enabled": True,
                    "credentials": [
                        {
                            "value": item["password"],
                            "type": "password",
                        }
                    ],
                }
            )
            logger.info("Created new passworded user %s", new_user)

            # Add Abacus-related roles to user
            assignViewRolesToUser(keycloak_admin, new_user)
        except Exception as e:
            logger.warning("Could not create passworded user %s!", item["username"])
            logger.warning(str(e))


def createUsersInRealm(keycloak_admin):
    for username in ("Alice_1234", "Bob_1234", "john"):
        try:
            new_user = keycloak_admin.create_user(
                {"username": username, "enabled": True}
            )
            logger.info("Created new user %s", new_user)
        except Exception as e:
            logger.warning("Could not create user %s!", username)
            logger.warning(str(e))
    passwordedUsers = os.getenv(
        "passwordUsers", "testuser@virtru.com,user1,user2"
    ).split(",")
    for passwordedUser in passwordedUsers:
        try:
            new_user = keycloak_admin.create_user(
                {
                    "username": passwordedUser,
                    "enabled": True,
                    "credentials": [
                        {
                            "value": "testuser123",
                            "type": "password",
                        }
                    ],
                }
            )
            logger.info("Created new passworded user %s", new_user)

            # Add Abacus-related roles to user
            assignViewRolesToUser(keycloak_admin, new_user)
        except Exception as e:
            logger.warning("Could not create passworded user %s!", username)
            logger.warning(str(e))


def addVirtruClientAudienceMapper(keycloak_admin, keycloak_client_id, client_audience):
    logger.info("Assigning client audience mapper to client %s", keycloak_client_id)
    try:
        keycloak_admin.add_mapper_to_client(
            keycloak_client_id,
            payload={
                "protocol": "openid-connect",
                "config": {
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                    "included.custom.audience": client_audience,
                },
                "name": f"Virtru {client_audience} Audience Mapper",
                "protocolMapper": "oidc-audience-mapper",
            },
        )
    except Exception as e:
        logger.warning(
            "Could not add client audience mapper to client %s - this likely means it is already there, so we can ignore this.",
            keycloak_client_id,
        )
        logger.warning(
            "Unfortunately python-keycloak doesn't seem to have a 'remove-mapper' function"
        )
        logger.warning(str(e))


def addVirtruMappers(keycloak_admin, keycloak_client_id):
    logger.info("Assigning custom mappers to client %s", keycloak_client_id)
    try:
        keycloak_admin.add_mapper_to_client(
            keycloak_client_id,
            payload={
                "protocol": "openid-connect",
                "config": {
                    "id.token.claim": "false",
                    "access.token.claim": "false",
                    "userinfo.token.claim": "true",
                    "remote.parameters.username": "true",
                    "remote.parameters.clientid": "true",
                    "client.publickey": "X-VirtruPubKey",
                    "claim.name": "tdf_claims",
                },
                "name": "Virtru OIDC UserInfo Mapper",
                "protocolMapper": "virtru-oidc-protocolmapper",
            },
        )
    except Exception as e:
        logger.warning(
            "Could not add custom userinfo mapper to client %s - this likely means it is already there, so we can ignore this.",
            keycloak_client_id,
        )
        logger.warning(
            "Unfortunately python-keycloak doesn't seem to have a 'remove-mapper' function"
        )
        logger.warning(str(e))
    try:
        keycloak_admin.add_mapper_to_client(
            keycloak_client_id,
            payload={
                "protocol": "openid-connect",
                "config": {
                    "id.token.claim": "true",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "false",
                    "remote.parameters.username": "true",
                    "remote.parameters.clientid": "true",
                    "client.publickey": "X-VirtruPubKey",
                    "claim.name": "tdf_claims",
                },
                "name": "Virtru OIDC Auth Mapper",
                "protocolMapper": "virtru-oidc-protocolmapper",
            },
        )
    except Exception as e:
        logger.warning(
            "Could not add custom auth mapper to client %s - this likely means it is already there, so we can ignore this.",
            keycloak_client_id,
        )
        logger.warning(
            "Unfortunately python-keycloak doesn't seem to have a 'remove-mapper' function"
        )
        logger.warning(str(e))


def addVirtruDCRSPIREMapper(keycloak_admin, keycloak_client_id):
    logger.info("Assigning custom SPIRE mapper to client %s", keycloak_client_id)
    try:
        keycloak_admin.add_mapper_to_client(
            keycloak_client_id,
            payload={
                "protocol": "openid-connect",
                "config": {
                    "id.token.claim": "true",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "true",
                    "user_workload.namespace": "default",
                    "user_workload.parentid": "spiffe://example.org/ns/spire/sa/spire-agent",
                    "user_workload.selectors": "k8s:pod-label:tdfdatacleanroom:enabled, k8s:ns:default"
                },
                "name": "DCR Spire Registration Mapper",
                "protocolMapper": "virtru-spire-protocolmapper",
            },
        )
    except Exception as e:
        logger.warning(
            "Could not add custom spire mapper to client %s - this likely means it is already there, so we can ignore this.",
            keycloak_client_id,
        )
        logger.warning(
            "Unfortunately python-keycloak doesn't seem to have a 'remove-mapper' function"
        )
        logger.warning(str(e))


def createTestClientForX509Flow(keycloak_admin):
    client_id = "client_x509"
    clients = keycloak_admin.get_clients()
    client_exist = check_matched({"clientId": client_id}, clients)
    if not client_exist:
        logger.debug("Creating client %s configured for x509 flow", client_id)
        keycloak_admin.create_client(
            payload={
                "clientId": client_id,
                "publicClient": "false",
                "standardFlowEnabled": "true",
                "directAccessGrantsEnabled": "true",
                "serviceAccountsEnabled": "true",
                "clientAuthenticatorType": "client-x509",
                "baseUrl": f"{otdf_frontend_url}/",
                "protocol": "openid-connect",
                "redirectUris": [f"{otdf_frontend_url}/*"],
                "webOrigins": ["+"],
                "attributes": {"x509.subjectdn": "CN=(.*)(?:$)"},
            },
            skip_exists=True,
        )

        keycloak_client_id = keycloak_admin.get_client_id(client_id)
        logger.info("Created client %s", keycloak_client_id)

        addVirtruMappers(keycloak_admin, keycloak_client_id)


def createTestClientForClientCredentialsFlow(
    keycloak_admin, keycloak_auth_url, client_id
):
    client_secret = os.getenv("CLIENT_SECRET", "123-456")
    logger.debug("Creating client %s configured for clientcreds flow", client_id)
    keycloak_admin.create_client(
        payload={
            "clientId": client_id,
            "directAccessGrantsEnabled": "true",
            "clientAuthenticatorType": "client-secret",
            "secret": client_secret,
            "serviceAccountsEnabled": "true",
            "publicClient": "false",
            "redirectUris": [keycloak_auth_url + "admin/" + client_id + "/console"],
            "attributes": {
                "user.info.response.signature.alg": "RS256"
            },  # Needed to make UserInfo return signed JWT
        },
        skip_exists=True,
    )

    keycloak_client_id = keycloak_admin.get_client_id(client_id)
    logger.info("Created client %s", keycloak_client_id)

    addVirtruMappers(keycloak_admin, keycloak_client_id)


def createTestClientForBrowserAuthFlow(keycloak_admin):
    client_id = "browsertest"
    logger.debug("Creating client %s configured for browser auth flow", client_id)
    keycloak_admin.create_client(
        payload={
            "clientId": client_id,
            "publicClient": "true",
            "standardFlowEnabled": "true",
            "baseUrl": f"{otdf_frontend_url}/",
            "protocol": "openid-connect",
            "redirectUris": [f"{otdf_frontend_url}/*"],
            "webOrigins": ["+"],
            "attributes": {
                "user.info.response.signature.alg": "RS256"
            },  # Needed to make UserInfo return signed JWT
        },
        skip_exists=True,
    )

    keycloak_client_id = keycloak_admin.get_client_id(client_id)
    logger.info("Created client %s", keycloak_client_id)

    addVirtruMappers(keycloak_admin, keycloak_client_id)


def createTestClientTDFClient(keycloak_admin):
    client_id = "tdf-client"
    logger.debug("Creating client %s configured for auth flow", client_id)
    keycloak_admin.create_client(
        payload={
            "clientId": client_id,
            "standardFlowEnabled": "true",
            "fullScopeAllowed": "false",
            "protocol": "openid-connect",
            "webOrigins": ["+"],
            "attributes": {
                "user.info.response.signature.alg": "RS256"
            },  # Needed to make UserInfo return signed JWT
        },
        skip_exists=True,
    )

    keycloak_client_id = keycloak_admin.get_client_id(client_id)
    logger.info("Created client %s", keycloak_client_id)

    addVirtruMappers(keycloak_admin, keycloak_client_id)
    addVirtruClientAudienceMapper(keycloak_admin, keycloak_client_id, "tdf-attributes")

def createPreloadedTDFClients(keycloak_admin, keycloak_auth_url, preloaded_clients):
    for item in preloaded_clients:
        logger.debug("Creating preloaded client %s configured for clientcreds flow", item["clientId"])
        keycloak_admin.create_client(
            payload={
                "clientId": item["clientId"],
                "directAccessGrantsEnabled": "true",
                "clientAuthenticatorType": "client-secret",
                "secret": item["clientSecret"],
                "serviceAccountsEnabled": "true",
                "publicClient": "false",
                "redirectUris": [keycloak_auth_url + "admin/" + item["clientId"] + "/console"],
                "attributes": {
                    "user.info.response.signature.alg": "RS256"
                },  # Needed to make UserInfo return signed JWT
            },
            skip_exists=True,
        )

        keycloak_client_id = keycloak_admin.get_client_id(item["clientId"])
        logger.info("Created client %s", keycloak_client_id)

        addVirtruMappers(keycloak_admin, keycloak_client_id)


def createTestClientTDFAttributes(keycloak_admin):
    client_id = "tdf-attributes"
    logger.debug("Creating client %s configured for browser auth flow", client_id)
    keycloak_admin.create_client(
        payload={
            "clientId": client_id,
            "publicClient": "true",
            "standardFlowEnabled": "true",
            "fullScopeAllowed": "false",
            "baseUrl": f"{otdf_frontend_url}/",
            "protocol": "openid-connect",
            "redirectUris": [f"{otdf_frontend_url}/*"],
            "webOrigins": ["+"],
            "attributes": {
                "user.info.response.signature.alg": "RS256"
            },  # Needed to make UserInfo return signed JWT
        },
        skip_exists=True,
    )

    keycloak_client_id = keycloak_admin.get_client_id(client_id)
    logger.info("Created client %s", keycloak_client_id)

    addVirtruMappers(keycloak_admin, keycloak_client_id)


def createTestClientTDFEntitlements(keycloak_admin):
    client_id = "tdf-entitlement"
    base_url = os.getenv("ENTITLEMENT_HOST", "http://localhost:4030").rstrip("/")
    logger.debug("Creating client %s configured for browser auth flow", client_id)
    keycloak_admin.create_client(
        payload={
            "clientId": client_id,
            "publicClient": "true",
            "standardFlowEnabled": "true",
            "fullScopeAllowed": "false",
            "baseUrl": f"{otdf_frontend_url}/",
            "protocol": "openid-connect",
            "redirectUris": [f"{otdf_frontend_url}/*"],
            "webOrigins": ["+"],
            "attributes": {
                "user.info.response.signature.alg": "RS256"
            },  # Needed to make UserInfo return signed JWT
        },
        skip_exists=True,
    )

    keycloak_client_id = keycloak_admin.get_client_id(client_id)
    logger.info("Created client %s", keycloak_client_id)

    addVirtruMappers(keycloak_admin, keycloak_client_id)


def createTestClientForAbacusWebAuth(keycloak_admin):
    client_id = "abacus-web"
    logger.debug("Creating client %s configured for Abacus auth flow", client_id)
    keycloak_admin.create_client(
        payload={
            "clientId": client_id,
            "publicClient": "true",
            "standardFlowEnabled": "true",
            "clientAuthenticatorType": "client-secret",
            "serviceAccountsEnabled": "true",
            "protocol": "openid-connect",
            "redirectUris": [f"{otdf_frontend_url}/*"],
            "webOrigins": ["+"],
        },
        skip_exists=True,
    )

    keycloak_client_id = keycloak_admin.get_client_id(client_id)
    logger.info("Created client %s", keycloak_client_id)

    addVirtruClientAudienceMapper(keycloak_admin, keycloak_client_id, "tdf-entitlement")
    addVirtruClientAudienceMapper(keycloak_admin, keycloak_client_id, "tdf-attributes")


def createTestClientForAbacusLocalAuth(keycloak_admin):
    client_id = "abacus-localhost"
    logger.debug("Creating client %s configured for Abacus auth flow", client_id)
    keycloak_admin.create_client(
        payload={
            "clientId": client_id,
            "publicClient": "true",
            "standardFlowEnabled": "true",
            "clientAuthenticatorType": "client-secret",
            "serviceAccountsEnabled": "true",
            "protocol": "openid-connect",
            "redirectUris": ["http://localhost:3000/*"],
            "webOrigins": ["+"],
        },
        skip_exists=True,
    )

    keycloak_client_id = keycloak_admin.get_client_id(client_id)
    logger.info("Created client %s", keycloak_client_id)

    addVirtruClientAudienceMapper(keycloak_admin, keycloak_client_id, "tdf-entitlement")
    addVirtruClientAudienceMapper(keycloak_admin, keycloak_client_id, "tdf-attributes")


def createTestClientForDCRAuth(keycloak_admin):
    client_id = "dcr-test"
    client_secret = "123-456"
    logger.debug("Creating public client %s configured for DCR Jupyter auth flow", client_id)
    keycloak_admin.create_client(
        payload={
            "clientId": client_id,
            "secret": client_secret,
            "publicClient": "true",
            "standardFlowEnabled": "true",
            "clientAuthenticatorType": "client-secret",
            "serviceAccountsEnabled": "true",
            "baseUrl": f"{otdf_frontend_url}",
            "protocol": "openid-connect",
            "redirectUris": [f"{otdf_frontend_url}/*"],
            "webOrigins": ["+"],
        },
        skip_exists=True,
    )

    keycloak_client_id = keycloak_admin.get_client_id(client_id)
    logger.info("Created client %s", keycloak_client_id)

    addVirtruClientAudienceMapper(keycloak_admin, keycloak_client_id, "tdf-entitlement")
    addVirtruClientAudienceMapper(keycloak_admin, keycloak_client_id, "tdf-attributes")

    addVirtruMappers(keycloak_admin, keycloak_client_id)
    addVirtruDCRSPIREMapper(keycloak_admin, keycloak_client_id)


def createTestClientForExchangeFlow(keycloak_admin, keycloak_auth_url):
    client_id = "exchange-target"
    client_secret = "12345678"
    logger.debug("Creating client %s configured for clientcreds flow", client_id)
    keycloak_admin.create_client(
        payload={
            "clientId": client_id,
            "directAccessGrantsEnabled": "true",
            "clientAuthenticatorType": "client-secret",
            "secret": client_secret,
            "serviceAccountsEnabled": "true",
            "publicClient": "false",
            "redirectUris": [f"{otdf_frontend_url}/*"],
            "attributes": {
                "user.info.response.signature.alg": "RS256"
            },  # Needed to make UserInfo return signed JWT
        },
        skip_exists=True,
    )

    keycloak_client_id = keycloak_admin.get_client_id(client_id)
    logger.info("Created client %s", keycloak_client_id)

    addVirtruMappers(keycloak_admin, keycloak_client_id)


def assignViewRolesToUser(keycloak_admin, user_id):

    realmManagerClient = keycloak_admin.get_client_id("realm-management")

    viewClients = keycloak_admin.get_client_role(realmManagerClient, "view-clients")
    viewUsers = keycloak_admin.get_client_role(realmManagerClient, "view-users")

    logger.info("Got viewClients role %s", viewClients)

    logger.info("Adding clients/users role to user %s", user_id)
    keycloak_admin.assign_client_role(
        user_id, realmManagerClient, roles=[viewClients, viewUsers]
    )


def createBrowserAuthFlowX509(keycloak_admin, realm_name, flow_name, provider_name):
    flows_auth = keycloak_admin.get_authentication_flows()
    flow_exist = check_matched({"alias": flow_name}, flows_auth)
    if not flow_exist:
        if provider_name == "auth-x509-client-username-form":
            keycloak_admin.copy_authentication_flow(
                payload={"newName": flow_name}, flow_alias="browser"
            )
        else:
            keycloak_admin.copy_authentication_flow(
                payload={"newName": flow_name}, flow_alias="direct grant"
            )

    flows_execution = keycloak_admin.get_authentication_flow_executions(flow_name)
    filtered_flow = check_matched({"providerId": provider_name}, flows_execution)
    if filtered_flow:
        payload_config = {
            "alias": flow_name + "_Config",
            "config": {
                "x509-cert-auth.canonical-dn-enabled": "false",
                "x509-cert-auth.mapper-selection.user-attribute-name": "usercertificate",
                "x509-cert-auth.serialnumber-hex-enabled": "false",
                "x509-cert-auth.regular-expression": "CN=(.*?)(?:$),",
                "x509-cert-auth.mapper-selection": "Username or Email",
                "x509-cert-auth.crl-relative-path": "crl.pem",
                "x509-cert-auth.crldp-checking-enabled": "false",
                "x509-cert-auth.mapping-source-selection": "Subject's Common Name",
                "x509-cert-auth.timestamp-validation-enabled": "true",
            },
        }
        flow_id = filtered_flow[0]["id"]
        params_path = {"realm-name": realm_name, "flow-id": flow_id}
        conn = keycloak_admin.connection
        conn.raw_post(
            URL_ADMIN_AUTHENTICATOR_EXECUTION_CONFIG.format(**params_path),
            data=json.dumps(payload_config),
        )

    if provider_name == "auth-x509-client-username-form":
        keycloak_admin.update_realm(realm_name, payload={"browserFlow": flow_name})
    else:
        # Make password auth for direct grants optional.
        # Otherwise, it'll require a password even if you have a client certificate.
        filtered_flow = check_matched(
            {"providerId": "direct-grant-validate-password"}, flows_execution
        )
        if filtered_flow:
            flow_id = filtered_flow[0]["id"]
            payload_config = {"id": flow_id, "requirement": "ALTERNATIVE"}
            params_path = {"realm-name": realm_name, "flow-alias": flow_name}
            conn = keycloak_admin.connection
            # We need to do this manually because KeycloakAdmin expects a 204 response and sometimes we get a valid 202.  :/
            conn.raw_put(
                URL_ADMIN_EXECUTION_FLOW.format(**params_path),
                data=json.dumps(payload_config),
            )
            keycloak_admin.update_realm(
                realm_name, payload={"directGrantFlow": flow_name}
            )


def createDirectAuthFlowX509(keycloak_admin, realm_name, flow_name, provider_name):
    flows_auth = keycloak_admin.get_authentication_flows()
    flow_exist = check_matched({"alias": flow_name}, flows_auth)
    if not flow_exist:
        if provider_name == "direct-grant-auth-x509-username":
            keycloak_admin.copy_authentication_flow(
                payload={"newName": flow_name}, flow_alias="direct grant"
            )

    data_direct_grant_flow_executions = keycloak_admin.get_authentication_flow_executions(flow_name)
    for key in data_direct_grant_flow_executions:
        if key.get('level') == 0:
            keycloak_admin.delete_authentication_flow_execution(key.get('id'))

    payload_config = {"provider": provider_name}
    params_path = {"realm-name": realm_name, "flow-alias": flow_name}
    conn = keycloak_admin.connection
    conn.raw_post(
        URL_ADMIN_EXECUTIONS_EXECUTION.format(**params_path),
        data=json.dumps(payload_config),
    )

    flows_execution = keycloak_admin.get_authentication_flow_executions(flow_name)
    filtered_flow = check_matched({"providerId": provider_name}, flows_execution)
    if filtered_flow:
        payload_config = {
            "alias": flow_name + "_Config",
            "config": {
                "x509-cert-auth.canonical-dn-enabled": "false",
                "x509-cert-auth.mapper-selection.user-attribute-name": "usercertificate",
                "x509-cert-auth.serialnumber-hex-enabled": "false",
                "x509-cert-auth.regular-expression": "CN=(.*?)(?:$),",
                "x509-cert-auth.mapper-selection": "Username or Email",
                "x509-cert-auth.crl-relative-path": "crl.pem",
                "x509-cert-auth.crldp-checking-enabled": "false",
                "x509-cert-auth.mapping-source-selection": "Subject's Common Name",
                "x509-cert-auth.timestamp-validation-enabled": "true",
            },
        }
        flow_id = filtered_flow[0]["id"]
        params_path = {"realm-name": realm_name, "flow-id": flow_id}
        conn = keycloak_admin.connection
        conn.raw_post(
            URL_ADMIN_AUTHENTICATOR_EXECUTION_CONFIG.format(**params_path),
            data=json.dumps(payload_config),
        )

    if provider_name == "direct-grant-auth-x509-username":
        keycloak_admin.update_realm(realm_name, payload={"directGrantFlow": flow_name})


def updateMasterRealm(kc_admin_user, kc_admin_pass, kc_url):
    logger.debug("Login admin %s %s", kc_url, kc_admin_user)
    keycloak_admin = KeycloakAdmin(
        server_url=kc_url,
        username=kc_admin_user,
        password=kc_admin_pass,
        realm_name="master",
    )

    # Create test client in `master` configured for Abacus cross-realm user/client queries
    createTestClientForAbacusWebAuth(keycloak_admin)
    createTestClientForAbacusLocalAuth(keycloak_admin)


def createTDFRealm(kc_admin_user, kc_admin_pass, kc_url, preloaded_clients, preloaded_users):
    realm_name = "tdf"

    logger.debug("Login admin %s %s", kc_url, kc_admin_user)
    keycloak_admin = KeycloakAdmin(
        server_url=kc_url,
        username=kc_admin_user,
        password=kc_admin_pass,
        realm_name="master",
    )

    realms = keycloak_admin.get_realms()
    realm_exist = check_matched({"realm": realm_name}, realms)
    if not realm_exist:
        logger.info("Create realm %s", realm_name)
        keycloak_admin.create_realm(
            # payload={"realm": realm_name, "enabled": "true", "attributes": {"frontendUrl": "http://keycloak-http:8080/auth/realms/tdf"}}, skip_exists=True
            payload={"realm": realm_name, "enabled": "true"},
            skip_exists=True,
        )

    keycloak_admin = KeycloakAdmin(
        server_url=kc_url,
        username=kc_admin_user,
        password=kc_admin_pass,
        realm_name=realm_name,
        user_realm_name="master",
    )

    # Create test client configured for clientcreds auth flow
    createTestClientForClientCredentialsFlow(keycloak_admin, kc_url, "tdf-client")
    npeClientStr = os.getenv("npeClients")
    if npeClientStr is not None:
        for npe_client_id in npeClientStr.split(","):
            createTestClientForClientCredentialsFlow(
                keycloak_admin, kc_url, npe_client_id
            )

    # Create test client configured for browser auth flow
    createTestClientForBrowserAuthFlow(keycloak_admin)

    # Create test client configured for exchange auth flow
    createTestClientForExchangeFlow(keycloak_admin, kc_url)

    # Create test client configured for exchange auth flow
    createTestClientForDCRAuth(keycloak_admin)

    # Create attributes test client
    createTestClientTDFAttributes(keycloak_admin)

    # Create entitlements test client
    createTestClientTDFEntitlements(keycloak_admin)

    createTestClientTDFClient(keycloak_admin)

    createTestClientForAbacusWebAuth(keycloak_admin)
    createTestClientForAbacusLocalAuth(keycloak_admin)

    #create preloaded clients
    if preloaded_clients is not None:
        createPreloadedTDFClients(keycloak_admin, kc_url, preloaded_clients)

    createUsersInRealm(keycloak_admin)

    #create preloaded users
    if preloaded_users is not None:
        createPreloadedUsersInRealm(keycloak_admin, preloaded_users)


def createTDFPKIRealm(kc_admin_user, kc_admin_pass, kc_url, preloaded_clients, preloaded_users):
    # BEGIN PKI
    realm_name = "tdf-pki"

    logger.debug("Login admin %s %s", kc_url, kc_admin_user)
    keycloak_admin = KeycloakAdmin(
        server_url=kc_url,
        username=kc_admin_user,
        password=kc_admin_pass,
        realm_name="master",
    )

    realms = keycloak_admin.get_realms()
    realm_exist = check_matched({"realm": realm_name}, realms)
    if not realm_exist:
        logger.info("Create realm %s", realm_name)
        keycloak_admin.create_realm(
            payload={
                "realm": realm_name,
                "enabled": "true",
                "attributes": {
                    "frontendUrl": f"{otdf_frontend_url}/auth/realms/tdf-pki"
                },
            },
            skip_exists=True,
        )

    keycloak_admin = KeycloakAdmin(
        server_url=kc_url,
        username=kc_admin_user,
        password=kc_admin_pass,
        realm_name=realm_name,
        user_realm_name="master",
    )

    # Create test client configured for clientcreds auth flow
    createTestClientForClientCredentialsFlow(keycloak_admin, kc_url, "tdf-client")

    # Create test client configured for browser auth flow
    createTestClientForBrowserAuthFlow(keycloak_admin)

    createTestClientForAbacusWebAuth(keycloak_admin)
    createTestClientForAbacusLocalAuth(keycloak_admin)

    if pki_direct == "true":
        # X.509 Client Certificate Authentication to a Direct Grant Flow
        # https://www.keycloak.org/docs/latest/server_admin/index.html#adding-x-509-client-certificate-authentication-to-a-direct-grant-flow
        createDirectAuthFlowX509(
            keycloak_admin,
            realm_name,
            "X509_Direct_Grant",
            "direct-grant-auth-x509-username",
        )

    if pki_browser == "true":
        # X.509 Client Certificate Authentication to a Browser Flow
        # https://www.keycloak.org/docs/latest/server_admin/index.html#adding-x-509-client-certificate-authentication-to-a-browser-flow
        createBrowserAuthFlowX509(
            keycloak_admin,
            realm_name,
            "X509_Browser",
            "auth-x509-client-username-form"
        )

    createTestClientForX509Flow(keycloak_admin)

    #create preloaded clients
    if preloaded_clients is not None:
        createPreloadedTDFClients(keycloak_admin, kc_url, preloaded_clients)

    createUsersInRealm(keycloak_admin)

    #create preloaded users
    if preloaded_users is not None:
        createPreloadedUsersInRealm(keycloak_admin, preloaded_users)    

    # END PKI

def findAndReplace(obj, str_to_find, replace_with):
    if type(obj) is str:
        return obj.replace(str_to_find, replace_with)
    elif type(obj) is list:
        new_list = []
        for item in obj:
            new_list.append(findAndReplace(item, str_to_find, replace_with))
        return new_list
    elif type(obj) is dict:
        new_dict = {}
        for k,v in obj.items():
            new_dict[k] = findAndReplace(v, str_to_find, replace_with)
        return new_dict
    else:
        return obj

def replaceYamlVars(config):
    # replace yaml vars
    config = findAndReplace(config, "{{ hostname }}", kc_internal_url)
    config = findAndReplace(config, "{{ externalUrl }}", otdf_frontend_url)
    return config


def addClientMappers(keycloak_admin, keycloak_client_id, mappers):
    for mapper in mappers:
        logger.info("Assigning mapper to client %s", keycloak_client_id)
        try:
            keycloak_admin.add_mapper_to_client(
                keycloak_client_id,
                payload=mapper,
            )
        except Exception as e:
            logger.warning(
                "Could not add client audience mapper to client %s - this likely means it is already there, so we can ignore this.",
                keycloak_client_id,
            )
            logger.warning(
                "Unfortunately python-keycloak doesn't seem to have a 'remove-mapper' function"
            )
            logger.warning(str(e))


def addRolesToUser(keycloak_admin, user_id, roles):
    realm_manager_client = keycloak_admin.get_client_id("realm-management")

    keycloak_roles = []
    for role in roles:
        keycloak_role = keycloak_admin.get_client_role(realm_manager_client, role)
        logger.info(f"Got {role} role {keycloak_role}")
        keycloak_roles.append(keycloak_role)

    if keycloak_roles:
        logger.info("Adding roles to user %s", user_id)
        keycloak_admin.assign_client_role(
            user_id, realm_manager_client, roles=keycloak_roles
        )


def createClient(keycloak_admin, realm_name, client):
    if "payload" not in client:
        logger.error("Client configs must have payloads")
        return
    try:
        client_id = client["payload"]["clientId"]
        logger.debug("Creating client %s", client_id)
        keycloak_admin.create_client(
            payload = client["payload"],
            skip_exists=True,
        )

        keycloak_client_id = keycloak_admin.get_client_id(client_id)
        logger.info("Created client %s", keycloak_client_id)

        if "mappers" in client:
            addClientMappers(keycloak_admin, keycloak_client_id, client["mappers"])

    except Exception as e:
        logger.error(f"Error creating client {client['payload']} in realm {realm_name}")
        logger.error(str(e))


def createUser(keycloak_admin, realm_name, user):
    if "payload" not in user:
        logger.error("User configs must have payloads")
        return
    try:
        new_user = keycloak_admin.create_user(
            user["payload"]
        )
        logger.info("Created new user %s", new_user)

        if "roles" in user:
            addRolesToUser(keycloak_admin, new_user, user["roles"])
    except Exception as e:
        logger.error(f"Error creating user {user['payload']}")
        logger.error(str(e))


def createRealm(keycloak_admin, realm_name, payload):
    logger.info("Creating realm %s", realm_name)
    realms = keycloak_admin.get_realms()
    realm_exist = check_matched({"realm": realm_name}, realms)
    if not realm_exist:
        keycloak_admin.create_realm(
            payload=payload,
            skip_exists=True,
        )
        logger.info("Created realm %s", realm_name)
    

def configureKeycloak(kc_admin_user, kc_admin_pass, kc_url, keycloak_config):
    for realm in keycloak_config:
        logger.debug("Login admin %s %s", kc_url, kc_admin_user)
        keycloak_admin = KeycloakAdmin(
            server_url=kc_url,
            username=kc_admin_user,
            password=kc_admin_pass,
            realm_name="master",
        )

        if "payload" in realm:
            createRealm(keycloak_admin, realm["name"], realm["payload"])
            keycloak_admin = KeycloakAdmin(
                server_url=kc_url,
                username=kc_admin_user,
                password=kc_admin_pass,
                realm_name=realm["name"],
                user_realm_name="master",
            )
        if "clients" in realm:
            for client in realm["clients"]:
                logger.debug(f"Client {client}")
                createClient(keycloak_admin, realm["name"], client)
        if "users" in realm:
            for user in realm["users"]:
                createUser(keycloak_admin, realm["name"], user)


def kc_bootstrap():
    username = os.getenv("keycloak_admin_username")
    password = os.getenv("keycloak_admin_password")

    keycloak_auth_url = kc_internal_url + "/auth/"

    # Contains a detailed keycloak configuration
    try:
        with open("/etc/virtru-config/config.yaml") as f:
            bootstrap_config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning("Not found: /etc/virtru-config/config.yaml", exc_info=1)
        bootstrap_config = None

    

    # use the custom config
    if bootstrap_config is not None:
        bootstrap_config = replaceYamlVars(bootstrap_config)
        configureKeycloak(username, password, keycloak_auth_url, bootstrap_config)
    # use our hardcoded config
    else:
        # Contains a list of clientIds and clientSecrets we want to preload
        try:
            with open("/etc/virtru-config/clients.yaml") as f:
                preloaded_clients = yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning("Not found: /etc/virtru-config/clients.yaml", exc_info=1)
            preloaded_clients = None

        # Contains a list of usernames and passwords we want to preload
        try:
            with open("/etc/virtru-config/users.yaml") as f:
                preloaded_users = yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning("Not found: /etc/virtru-config/users.yaml", exc_info=1)
            preloaded_users = None

        updateMasterRealm(username, password, keycloak_auth_url)

        
        createTDFRealm(username, password, keycloak_auth_url, preloaded_clients, preloaded_users)

        # If either browser PKI or direct grant PKI configured, create PKI realm
        if ((pki_browser == "true") or (pki_direct == "true")):
            createTDFPKIRealm(username, password, keycloak_auth_url, preloaded_clients, preloaded_users)

    return True  # It is pointless to return True here, as we arent' checking the return values of the previous calls (and don't really need to)
