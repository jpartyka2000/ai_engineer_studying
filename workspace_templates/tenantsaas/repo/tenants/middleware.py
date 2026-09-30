"""Resolves the current tenant from the request's API key."""

import logging

from django.http import JsonResponse

from tenants.context import clear_current_tenant, set_current_tenant_id
from tenants.models import Tenant

logger = logging.getLogger(__name__)

API_KEY_HEADER = "HTTP_X_API_KEY"

# Paths that legitimately have no tenant.
PUBLIC_PATHS = ("/healthz", "/readyz")


class TenantMiddleware:
    """Attach the authenticated tenant to the request and to the context var.

    The context var is cleared in a ``finally`` block. Without that, a worker thread
    reused for the next request could inherit the previous tenant -- which would be
    a cross-tenant leak rather than merely a bug.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path in PUBLIC_PATHS:
            return self.get_response(request)

        api_key = request.META.get(API_KEY_HEADER, "")
        if not api_key:
            return JsonResponse({"error": "X-Api-Key header is required"}, status=401)

        tenant = Tenant.objects.filter(api_key=api_key, is_active=True).first()
        if tenant is None:
            logger.warning("rejected request with unknown api key")
            return JsonResponse({"error": "Unknown or inactive API key"}, status=403)

        request.tenant = tenant
        set_current_tenant_id(tenant.pk)
        try:
            return self.get_response(request)
        finally:
            clear_current_tenant()
