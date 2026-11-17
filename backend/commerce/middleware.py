from django.middleware.csrf import CsrfViewMiddleware
import json
import logging
import time
import uuid

request_logger=logging.getLogger('productstat.requests')

class RequestContextMiddleware:
    """Correlatable logs without query strings, customer payloads or provider secrets."""
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        started=time.monotonic()
        try: request_id=str(uuid.UUID(request.headers.get('X-Request-ID','')))
        except (ValueError,TypeError,AttributeError): request_id=str(uuid.uuid4())
        request.request_id=request_id
        response=self.get_response(request)
        response['X-Request-ID']=request_id
        request_logger.info(json.dumps({'event':'http_request','request_id':request_id,'method':request.method,'path':request.path,'status':response.status_code,'duration_ms':round((time.monotonic()-started)*1000,2)},separators=(',',':')))
        return response

class APICSRFMiddleware:
    """DRF sessions enforce CSRF only for authenticated users; protect guest mutations too."""
    def __init__(self,get_response):
        self.get_response=get_response
        self.csrf=CsrfViewMiddleware(get_response)
    def __call__(self,request):
        if request.path.startswith('/api/v1/') and request.path not in ['/api/v1/payments/sslcommerz/ipn/','/api/v1/payments/sslcommerz/return/'] and request.method not in ['GET','HEAD','OPTIONS','TRACE']:
            rejection=self.csrf.process_view(request,lambda request:None,(),{})
            if rejection: return rejection
        return self.get_response(request)
