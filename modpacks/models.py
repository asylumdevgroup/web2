from django.db import models
from django.utils import timezone


class Modpack(models.Model):
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=255, unique=True)
    curseforge_url = models.URLField()
    project_id = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    minecraft_version = models.CharField(max_length=50, blank=True)
    modloader = models.CharField(max_length=50, blank=True)
    image_url = models.URLField(blank=True)
    downloads = models.IntegerField(default=0)
    followers = models.IntegerField(default=0)
    last_updated = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-last_updated']
    
    def __str__(self):
        return self.name
    
    def soft_delete(self):
        """Soft delete the modpack and free up the ID for reuse"""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.is_active = False
        self.save()
    
    @classmethod
    def get_next_available_id(cls):
        """Get the next available ID for reuse"""
        # Find the lowest deleted ID that can be reused
        deleted_modpack = cls.objects.filter(is_deleted=True).order_by('id').first()
        if deleted_modpack:
            return deleted_modpack.id
        return None
    
    @classmethod
    def create_with_reused_id(cls, **kwargs):
        """Create a modpack with a reused ID if available"""
        reused_id = cls.get_next_available_id()
        if reused_id:
            # Get the existing deleted modpack to preserve some fields
            deleted_modpack = cls.objects.get(id=reused_id)
            
            # Update the deleted modpack with new data
            for key, value in kwargs.items():
                setattr(deleted_modpack, key, value)
            
            # Reset deletion fields
            deleted_modpack.is_deleted = False
            deleted_modpack.deleted_at = None
            deleted_modpack.created_at = timezone.now()  # Set new creation time
            
            deleted_modpack.save()
            return deleted_modpack
        else:
            # Create normally with auto-generated ID
            return cls.objects.create(**kwargs)


class ScrapingTask(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    name = models.CharField(max_length=255)
    curseforge_url = models.CharField(max_length=10, help_text="CurseForge project ID")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    modpacks_found = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - {self.status}"


class ModDependency(models.Model):
    """Store mod dependencies for faster access"""
    modpack = models.ForeignKey(Modpack, on_delete=models.CASCADE, related_name='dependencies')
    mod_id = models.CharField(max_length=20)
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=255, blank=True)
    summary = models.TextField(blank=True, null=True)
    logo_url = models.URLField(blank=True)
    author = models.CharField(max_length=255, blank=True)
    download_count = models.IntegerField(default=0)
    date_created = models.DateTimeField(null=True, blank=True)
    date_modified = models.DateTimeField(null=True, blank=True)
    date_released = models.DateTimeField(null=True, blank=True)
    website_url = models.URLField(blank=True)
    curseforge_url = models.URLField(blank=True)
    last_fetched = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        unique_together = ['modpack', 'mod_id']
    
    def __str__(self):
        return f"{self.name} ({self.modpack.name})"


class SiteAnalytics(models.Model):
    """Track web traffic analytics"""
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    country = models.CharField(max_length=100, blank=True)
    page_url = models.CharField(max_length=500)
    referrer = models.CharField(max_length=500, blank=True)
    session_id = models.CharField(max_length=100, blank=True)
    is_unique_visit = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Site Analytics'
    
    def __str__(self):
        return f"{self.ip_address} - {self.page_url} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"
    
    @classmethod
    def record_hit(cls, request, page_url):
        """Record a site hit with analytics"""
        from django.utils import timezone
        from datetime import timedelta
        
        # Get IP address
        ip_address = cls._get_client_ip(request)
        
        # Get session ID
        session_id = request.session.session_key or ''
        
        # Check if this is a unique visit (same IP, different session, or 24h gap)
        is_unique = cls._is_unique_visit(ip_address, session_id)
        
        # Get country (simplified - you could use a geolocation service)
        country = cls._get_country_from_ip(ip_address)
        
        # Create analytics record
        analytics = cls.objects.create(
            ip_address=ip_address,
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            country=country,
            page_url=page_url,
            referrer=request.META.get('HTTP_REFERER', ''),
            session_id=session_id,
            is_unique_visit=is_unique
        )
        
        return analytics
    
    @classmethod
    def _get_client_ip(cls, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    @classmethod
    def _is_unique_visit(cls, ip_address, session_id):
        """Check if this is a unique visit"""
        from django.utils import timezone
        from datetime import timedelta
        
        # Check for visits from same IP in last 24 hours
        yesterday = timezone.now() - timedelta(hours=24)
        recent_visits = cls.objects.filter(
            ip_address=ip_address,
            created_at__gte=yesterday
        ).count()
        
        return recent_visits == 0
    
    @classmethod
    def _get_country_from_ip(cls, ip_address):
        """Get country from IP (simplified implementation)"""
        # This is a simplified version - you could integrate with a real geolocation service
        # For now, we'll return 'Unknown' - you could use services like:
        # - ipapi.co
        # - ipinfo.io
        # - maxmind.com
        return 'Unknown'
    
    @classmethod
    def get_analytics_summary(cls):
        """Get analytics summary for dashboard"""
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        today = now.date()
        yesterday = today - timedelta(days=1)
        last_week = today - timedelta(days=7)
        last_month = today - timedelta(days=30)
        
        return {
            'total_hits': cls.objects.count(),
            'unique_hits': cls.objects.filter(is_unique_visit=True).count(),
            'today_hits': cls.objects.filter(created_at__date=today).count(),
            'today_unique': cls.objects.filter(created_at__date=today, is_unique_visit=True).count(),
            'yesterday_hits': cls.objects.filter(created_at__date=yesterday).count(),
            'yesterday_unique': cls.objects.filter(created_at__date=yesterday, is_unique_visit=True).count(),
            'week_hits': cls.objects.filter(created_at__date__gte=last_week).count(),
            'week_unique': cls.objects.filter(created_at__date__gte=last_week, is_unique_visit=True).count(),
            'month_hits': cls.objects.filter(created_at__date__gte=last_month).count(),
            'month_unique': cls.objects.filter(created_at__date__gte=last_month, is_unique_visit=True).count(),
            'top_countries': cls.objects.values('country').annotate(
                count=models.Count('id')
            ).order_by('-count')[:10],
            'top_pages': cls.objects.values('page_url').annotate(
                count=models.Count('id')
            ).order_by('-count')[:10],
        }
