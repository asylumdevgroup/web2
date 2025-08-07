from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.utils import timezone
from django.contrib.admin import SimpleListFilter
from .models import Modpack, ScrapingTask, SiteAnalytics
from .scraper import CurseForgeAPI
import threading
import time


class ModloaderFilter(SimpleListFilter):
    title = 'Modloader'
    parameter_name = 'modloader_filter'

    def lookups(self, request, model_admin):
        return (
            ('forge', 'Forge'),
            ('neoforge', 'NeoForge'),
            ('fabric', 'Fabric'),
            ('quilt', 'Quilt'),
            ('unknown', 'Unknown/Empty'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'forge':
            return queryset.filter(modloader__icontains='forge')
        elif self.value() == 'neoforge':
            return queryset.filter(modloader__icontains='neoforge')
        elif self.value() == 'fabric':
            return queryset.filter(modloader__icontains='fabric')
        elif self.value() == 'quilt':
            return queryset.filter(modloader__icontains='quilt')
        elif self.value() == 'unknown':
            return queryset.filter(modloader__isnull=True) | queryset.filter(modloader='')
        return queryset


class MinecraftVersionFilter(SimpleListFilter):
    title = 'Minecraft Version'
    parameter_name = 'minecraft_version_filter'

    def lookups(self, request, model_admin):
        return (
            ('1.12.2', '1.12.2'),
            ('1.21.1', '1.21.1'),
            ('1.20.x', '1.20.x'),
            ('1.19.x', '1.19.x'),
            ('1.18.x', '1.18.x'),
            ('1.16.x', '1.16.x'),
            ('other', 'Other/Unknown'),
        )

    def queryset(self, request, queryset):
        if self.value() == '1.12.2':
            return queryset.filter(minecraft_version='1.12.2')
        elif self.value() == '1.21.1':
            return queryset.filter(minecraft_version='1.21.1')
        elif self.value() == '1.20.x':
            return queryset.filter(minecraft_version__startswith='1.20')
        elif self.value() == '1.19.x':
            return queryset.filter(minecraft_version__startswith='1.19')
        elif self.value() == '1.18.x':
            return queryset.filter(minecraft_version__startswith='1.18')
        elif self.value() == '1.16.x':
            return queryset.filter(minecraft_version__startswith='1.16')
        elif self.value() == 'other':
            return queryset.exclude(minecraft_version__in=['1.12.2', '1.21.1']).exclude(
                minecraft_version__startswith='1.20'
            ).exclude(minecraft_version__startswith='1.19').exclude(
                minecraft_version__startswith='1.18'
            ).exclude(minecraft_version__startswith='1.16')
        return queryset


class DownloadsFilter(SimpleListFilter):
    title = 'Downloads'
    parameter_name = 'downloads_filter'

    def lookups(self, request, model_admin):
        return (
            ('0-100', '0-100'),
            ('100-1000', '100-1,000'),
            ('1000-10000', '1,000-10,000'),
            ('10000+', '10,000+'),
        )

    def queryset(self, request, queryset):
        if self.value() == '0-100':
            return queryset.filter(downloads__lte=100)
        elif self.value() == '100-1000':
            return queryset.filter(downloads__gt=100, downloads__lte=1000)
        elif self.value() == '1000-10000':
            return queryset.filter(downloads__gt=1000, downloads__lte=10000)
        elif self.value() == '10000+':
            return queryset.filter(downloads__gt=10000)
        return queryset


@admin.register(Modpack)
class ModpackAdmin(admin.ModelAdmin):
    list_display = ['name', 'minecraft_version', 'modloader', 'downloads', 'followers', 'last_updated', 'is_active']
    list_filter = ['is_active', 'last_updated', ModloaderFilter, MinecraftVersionFilter, DownloadsFilter]
    search_fields = ['name', 'description', 'slug']
    readonly_fields = ['created_at', 'last_updated', 'project_id']
    list_editable = ['is_active']
    list_per_page = 25
    
    actions = ['refresh_selected_modpacks', 'activate_selected', 'deactivate_selected']
    
    def refresh_selected_modpacks(self, request, queryset):
        """Refresh data for selected modpacks"""
        count = 0
        for modpack in queryset:
            try:
                if modpack.project_id:
                    # Import the function here to avoid circular imports
                    from .views import fetch_curseforge_data
                    data = fetch_curseforge_data(modpack.project_id)
                    if data['success']:
                        if data.get('name'):
                            modpack.name = data['name']
                        if data.get('description'):
                            modpack.description = data['description']
                        if data.get('summary'):
                            modpack.summary = data['summary']
                        if data.get('image_url'):
                            modpack.image_url = data['image_url']
                        if data.get('minecraft_version'):
                            modpack.minecraft_version = data['minecraft_version']
                        if data.get('modloader'):
                            modpack.modloader = data['modloader'] or 'Unknown'
                        if data.get('website_url'):
                            modpack.curseforge_url = data['website_url']
                        if data.get('downloads'):
                            modpack.downloads = data['downloads']
                        if data.get('followers'):
                            modpack.followers = data['followers']
                        
                        modpack.last_updated = timezone.now()
                        modpack.save()
                        count += 1
            except Exception as e:
                self.message_user(request, f"Error refreshing {modpack.name}: {str(e)}", level=messages.ERROR)
        
        self.message_user(request, f"Successfully refreshed {count} modpack(s)")
    
    refresh_selected_modpacks.short_description = "Refresh selected modpacks from CurseForge"
    
    def activate_selected(self, request, queryset):
        """Activate selected modpacks"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Activated {updated} modpack(s)")
    
    activate_selected.short_description = "Activate selected modpacks"
    
    def deactivate_selected(self, request, queryset):
        """Deactivate selected modpacks"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {updated} modpack(s)")
    
    deactivate_selected.short_description = "Deactivate selected modpacks"
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'curseforge_url', 'description')
        }),
        ('Version Information', {
            'fields': ('minecraft_version', 'modloader')
        }),
        ('Media', {
            'fields': ('image_url',)
        }),
        ('Statistics', {
            'fields': ('downloads', 'followers')
        }),
        ('Status', {
            'fields': ('is_active', 'created_at', 'last_updated')
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing an existing object
            return self.readonly_fields + ('slug',)
        return self.readonly_fields


@admin.register(ScrapingTask)
class ScrapingTaskAdmin(admin.ModelAdmin):
    list_display = ['name', 'status', 'modpacks_found', 'created_at', 'started_at', 'completed_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'curseforge_url']
    readonly_fields = ['status', 'started_at', 'completed_at', 'error_message', 'modpacks_found']
    
    fieldsets = (
        ('Task Information', {
            'fields': ('name', 'curseforge_url')
        }),
        ('Status Information', {
            'fields': ('status', 'started_at', 'completed_at', 'error_message', 'modpacks_found')
        }),
    )
    
    actions = ['run_scraping_task']
    
    def run_scraping_task(self, request, queryset):
        """Run the selected scraping tasks"""
        for task in queryset:
            if task.status == 'pending':
                # Start scraping in a background thread
                thread = threading.Thread(target=self._run_scraping_task, args=(task,))
                thread.daemon = True
                thread.start()
        
        self.message_user(request, f"Started {queryset.count()} scraping task(s)")
        return HttpResponseRedirect(request.get_full_path())
    
    run_scraping_task.short_description = "Run selected scraping tasks"


@admin.register(SiteAnalytics)
class SiteAnalyticsAdmin(admin.ModelAdmin):
    list_display = ['ip_address', 'country', 'page_url', 'is_unique_visit', 'created_at']
    list_filter = ['is_unique_visit', 'country', 'created_at']
    search_fields = ['ip_address', 'page_url', 'user_agent']
    readonly_fields = ['ip_address', 'user_agent', 'country', 'page_url', 'referrer', 'session_id', 'is_unique_visit', 'created_at']
    list_per_page = 50
    
    def has_add_permission(self, request):
        return False  # Don't allow manual creation
    
    def has_change_permission(self, request, obj=None):
        return False  # Don't allow editing
    
    def has_delete_permission(self, request, obj=None):
        return True  # Allow deletion for cleanup
    
    def _run_scraping_task(self, task):
        """Run a scraping task in the background"""
        try:
            # Update task status
            task.status = 'running'
            task.started_at = timezone.now()
            task.save()
            
            scraper = CurseForgeScraper()
            modpacks_found = 0
            
            # Check if it's a single modpack URL or a list URL
            if '/projects/' in task.curseforge_url:
                # Single modpack
                modpack_data = scraper.scrape_modpack_page(task.curseforge_url)
                if modpack_data:
                    scraper.save_modpack(modpack_data)
                    modpacks_found = 1
            else:
                # List of modpacks
                modpack_links = scraper.scrape_modpack_list(task.curseforge_url)
                
                for link_data in modpack_links:
                    modpack_data = scraper.scrape_modpack_page(link_data['curseforge_url'])
                    if modpack_data:
                        scraper.save_modpack(modpack_data)
                        modpacks_found += 1
                    
                    # Add a small delay to be respectful to the server
                    time.sleep(1)
            
            # Update task status
            task.status = 'completed'
            task.completed_at = timezone.now()
            task.modpacks_found = modpacks_found
            task.save()
            
        except Exception as e:
            # Update task status on error
            task.status = 'failed'
            task.completed_at = timezone.now()
            task.error_message = str(e)
            task.save()


# Custom admin site
class AsylumAdminSite(admin.AdminSite):
    site_header = "Asylum Dev - Modpack Manager"
    site_title = "Asylum Dev Admin"
    index_title = "Welcome to Asylum Dev Modpack Manager"
    
    def get_app_list(self, request):
        app_list = super().get_app_list(request)
        
        # Add custom dashboard stats
        modpack_count = Modpack.objects.count()
        active_modpacks = Modpack.objects.filter(is_active=True).count()
        pending_tasks = ScrapingTask.objects.filter(status='pending').count()
        
        # Add stats to the first app
        if app_list:
            app_list[0]['models'].append({
                'name': 'dashboard_stats',
                'object_name': 'dashboard_stats',
                'admin_url': '#',
                'view_only': True,
                'perms': {'view': True},
                'count': {
                    'total_modpacks': modpack_count,
                    'active_modpacks': active_modpacks,
                    'pending_tasks': pending_tasks,
                }
            })
        
        return app_list


# Create custom admin site instance
asylum_admin_site = AsylumAdminSite(name='asylum_admin')

# Register models with custom admin site
asylum_admin_site.register(Modpack, ModpackAdmin)
asylum_admin_site.register(ScrapingTask, ScrapingTaskAdmin)
