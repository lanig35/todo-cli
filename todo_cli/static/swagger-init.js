// Swagger UI sur le document OpenAPI du serveur (adresse relative : fonctionne derrière un proxy).
window.ui = SwaggerUIBundle({
  url: "openapi.json",
  dom_id: "#swagger-ui",
  deepLinking: true,
  tryItOutEnabled: false
});
