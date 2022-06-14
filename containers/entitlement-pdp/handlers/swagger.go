package handlers

import (
	"fmt"
	"net/http"

	httpSwagger "github.com/swaggo/http-swagger"  // http-swagger middleware
	_ "github.com/virtru/v2/entitlement-pdp/docs" // docs is generated by Swag CLI, you have to import it.
)

func GetSwaggerHandler(address string) http.Handler {

	return httpSwagger.Handler(
		httpSwagger.URL(fmt.Sprintf("http://%s/docs/doc.json", address)), //The url pointing to API definition
	)
}