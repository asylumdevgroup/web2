from django.utils.deprecation import MiddlewareMixin
from .models import SiteAnalytics

class AnalyticsMiddleware(MiddlewareMixin):
    """Middleware to track page hits for analytics"""
    
    def process_request(self, request):
        """Record page hit before processing request"""
        # Skip tracking for admin pages and static files
        if request.path.startswith('/admin/') or request.path.startswith('/static/'):
            return None
        
        # Skip tracking for staff-only pages if user is not staff
        if request.path.startswith('/staff/') and not (hasattr(request, 'user') and request.user.is_staff):
            return None
        
        try:
            # Record the page hit
            SiteAnalytics.record_hit(request, request.path)
        except Exception as e:
            # Don't let analytics errors break the site
            print(f"Analytics error: {e}")
        
        return None 