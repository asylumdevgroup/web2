from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import models
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import Modpack, ScrapingTask, ModDependency, SiteAnalytics
from .scraper import CurseForgeAPI
import json
import threading
import time
import re
import requests
import threading
import time
import re
from datetime import datetime, timedelta, timezone
from django.utils import timezone as django_timezone


def modpack_list(request):
    """Display list of all modpacks"""
    modpacks = Modpack.objects.filter(is_deleted=False, is_active=True).order_by('-last_updated')
    
    # Get filter parameters
    search_query = request.GET.get('search', '')
    mc_version = request.GET.get('mc_version', '')
    modloader = request.GET.get('modloader', '')
    
    # Apply filters
    if search_query:
        modpacks = modpacks.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    if mc_version:
        modpacks = modpacks.filter(minecraft_version=mc_version)
    
    if modloader:
        modpacks = modpacks.filter(modloader=modloader)
    
    # Get unique values for dropdown filters
    minecraft_versions = Modpack.objects.filter(
        is_deleted=False, 
        is_active=True,
        minecraft_version__isnull=False
    ).exclude(minecraft_version='').values_list('minecraft_version', flat=True).distinct().order_by('minecraft_version')
    
    modloaders = Modpack.objects.filter(
        is_deleted=False, 
        is_active=True,
        modloader__isnull=False
    ).exclude(modloader='').exclude(modloader='Unknown').values_list('modloader', flat=True).distinct().order_by('modloader')
    
    # Pagination
    paginator = Paginator(modpacks, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'mc_version': mc_version,
        'modloader': modloader,
        'minecraft_versions': minecraft_versions,
        'modloaders': modloaders,
    }
    
    return render(request, 'modpacks/modpack_list.html', context)


def modpack_detail(request, slug):
    """Display detailed view of a specific modpack"""
    modpack = get_object_or_404(Modpack, slug=slug, is_deleted=False, is_active=True)
    
    # Get related modpacks (same minecraft version and modloader)
    related_modpacks = Modpack.objects.filter(
        minecraft_version=modpack.minecraft_version,
        modloader=modpack.modloader,
        is_deleted=False,
        is_active=True
    ).exclude(id=modpack.id)[:6]
    
    # Fetch latest 3 files for the modpack
    latest_files = []
    if modpack.project_id:
        try:
            files_data = fetch_modpack_files(modpack.project_id)
            if files_data['success'] and files_data['files']:
                latest_files = files_data['files'][:3]  # Get latest 3 files
        except Exception as e:
            print(f"Error fetching files for modpack {modpack.id}: {e}")
    
    context = {
        'modpack': modpack,
        'related_modpacks': related_modpacks,
        'latest_files': latest_files
    }
    
    return render(request, 'modpacks/modpack_detail.html', context)


def home(request):
    """Home page with featured modpacks"""
    featured_modpacks = Modpack.objects.filter(is_active=True).order_by('-downloads')[:6]
    recent_modpacks = Modpack.objects.filter(is_active=True).order_by('-last_updated')[:6]
    
    context = {
        'featured_modpacks': featured_modpacks,
        'recent_modpacks': recent_modpacks,
    }
    
    return render(request, 'modpacks/home.html', context)


def custom_login(request):
    """Custom login page"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None and user.is_staff:
            login(request, user)
            return redirect('admin_dashboard')
        else:
            return render(request, 'modpacks/login.html', {
                'error': 'Invalid credentials or insufficient permissions.'
            })
    
    return render(request, 'modpacks/login.html')


def custom_logout(request):
    """Custom logout"""
    logout(request)
    return redirect('modpacks:home')


@login_required
def admin_dashboard(request):
    """Custom admin dashboard"""
    if not request.user.is_staff:
        return redirect('modpacks:home')
    
    total_modpacks = Modpack.objects.filter(is_deleted=False).count()
    active_modpacks = Modpack.objects.filter(is_deleted=False, is_active=True).count()
    pending_tasks = ScrapingTask.objects.filter(status='pending').count()
    completed_tasks = ScrapingTask.objects.filter(status='completed').count()
    failed_tasks = ScrapingTask.objects.filter(status='failed').count()
    total_tasks = ScrapingTask.objects.count()
    recent_modpacks = Modpack.objects.filter(is_deleted=False).order_by('-created_at')[:5]
    recent_tasks = ScrapingTask.objects.order_by('-created_at')[:5]
    
    context = {
        'total_modpacks': total_modpacks,
        'active_modpacks': active_modpacks,
        'pending_tasks': pending_tasks,
        'completed_tasks': completed_tasks,
        'failed_tasks': failed_tasks,
        'total_tasks': total_tasks,
        'recent_modpacks': recent_modpacks,
        'recent_tasks': recent_tasks,
    }
    
    return render(request, 'modpacks/admin_dashboard.html', context)


@login_required
def admin_modpacks(request):
    """Custom admin modpacks management"""
    if not request.user.is_staff:
        return redirect('modpacks:home')
    
    modpacks = Modpack.objects.filter(is_deleted=False).order_by('-created_at')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        modpacks = modpacks.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(modpacks, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
    }
    
    return render(request, 'modpacks/admin_modpacks.html', context)


@login_required
def admin_tasks(request):
    """Custom admin scraping tasks management"""
    if not request.user.is_staff:
        return redirect('modpacks:home')
    
    tasks = ScrapingTask.objects.all().order_by('-created_at')
    
    context = {
        'tasks': tasks,
    }
    
    return render(request, 'modpacks/admin_tasks.html', context)


@csrf_exempt
@login_required
def api_run_task(request, task_id):
    """API endpoint to run a scraping task"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        task = ScrapingTask.objects.get(id=task_id)
        
        # Reset task to pending status if it's completed or failed
        if task.status in ['completed', 'failed']:
            task.status = 'pending'
            task.started_at = None
            task.completed_at = None
            task.error_message = None
            task.modpacks_found = 0
            task.save()
        
        if task.status != 'pending':
            return JsonResponse({'error': 'Task is not in pending status'}, status=400)
        
        # Start scraping in background thread
        thread = threading.Thread(target=_run_scraping_task, args=(task,))
        thread.daemon = True
        thread.start()
        
        return JsonResponse({
            'success': True,
            'message': 'Task started successfully'
        })
        
    except ScrapingTask.DoesNotExist:
        return JsonResponse({'error': 'Task not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _run_scraping_task(task):
    """Run a scraping task in the background and create/update modpacks"""
    try:
        # Update task status
        task.status = 'running'
        task.started_at = datetime.now(timezone.utc)
        task.save()
        
        modpacks_found = 0
        
        # Handle project ID directly
        project_id = task.curseforge_url.strip()
        
        # Check if it's a valid project ID (numeric)
        if project_id.isdigit():
            print(f"Running scraping task for project ID: {project_id}")
            
            # Use the new CurseTools API to fetch data
            curseforge_data = fetch_curseforge_data(project_id)
            
            if curseforge_data['success']:
                # Generate slug from name
                import re
                name = curseforge_data.get('name') or task.name
                if not name:
                    name = f"modpack-{project_id}"  # Fallback name
                
                slug = re.sub(r'[^a-z0-9\s-]', '', name.lower())
                slug = re.sub(r'\s+', '-', slug)
                slug = re.sub(r'-+', '-', slug).strip('-')
                
                # Create CurseForge URL
                curseforge_url = f"https://www.curseforge.com/minecraft/modpacks/{project_id}"
                
                # Create or update modpack using ID reuse
                try:
                    # Try to find existing modpack by slug first
                    existing_modpack = Modpack.objects.filter(slug=slug, is_deleted=False).first()
                    
                    # If not found by slug, try to find by CurseForge project ID
                    if not existing_modpack:
                        existing_modpack = Modpack.objects.filter(
                            curseforge_url__contains=f"/{project_id}",
                            is_deleted=False
                        ).first()
                    
                    if existing_modpack:
                        # Update existing modpack
                        existing_modpack.name = curseforge_data.get('name', task.name)
                        existing_modpack.slug = slug  # Update slug in case it changed
                        existing_modpack.curseforge_url = curseforge_data.get('website_url') or curseforge_url
                        existing_modpack.project_id = project_id  # Store project ID
                        existing_modpack.description = curseforge_data.get('description', '')  # Full description
                        existing_modpack.summary = curseforge_data.get('summary', '')  # Short summary
                        existing_modpack.image_url = curseforge_data.get('image_url', '')
                        existing_modpack.minecraft_version = curseforge_data.get('minecraft_version', '')
                        existing_modpack.modloader = curseforge_data.get('modloader', '') or 'Unknown'
                        existing_modpack.downloads = curseforge_data.get('downloads', 0)
                        existing_modpack.followers = curseforge_data.get('followers', 0)
                        existing_modpack.last_updated = datetime.now(timezone.utc)
                        existing_modpack.is_active = True
                        existing_modpack.save()
                        modpack = existing_modpack
                        created = False
                        print(f"Updated existing modpack: {modpack.name} (ID: {modpack.id})")
                    else:
                        # Create new modpack with ID reuse
                        modpack = Modpack.create_with_reused_id(
                            name=curseforge_data.get('name', task.name),
                            slug=slug,
                            curseforge_url=curseforge_data.get('website_url') or curseforge_url,
                            project_id=project_id,  # Store project ID
                            description=curseforge_data.get('description', ''),  # Full description
                            summary=curseforge_data.get('summary', ''),  # Short summary
                            image_url=curseforge_data.get('image_url', ''),
                            minecraft_version=curseforge_data.get('minecraft_version', ''),
                            modloader=curseforge_data.get('modloader', '') or 'Unknown',
                            downloads=curseforge_data.get('downloads', 0),
                            followers=curseforge_data.get('followers', 0),
                            last_updated=datetime.now(timezone.utc),
                            is_active=True
                        )
                        created = True
                        print(f"Created new modpack: {modpack.name} (ID: {modpack.id})")
                except Exception as e:
                    print(f"Error creating/updating modpack: {e}")
                    # Fallback to normal creation
                    modpack = Modpack.objects.create(
                        name=curseforge_data.get('name', task.name),
                        slug=slug,
                        curseforge_url=curseforge_data.get('website_url') or curseforge_url,
                        project_id=project_id,  # Store project ID
                        description=curseforge_data.get('description', ''),  # Full description
                        summary=curseforge_data.get('summary', ''),  # Short summary
                        image_url=curseforge_data.get('image_url', ''),
                        minecraft_version=curseforge_data.get('minecraft_version', ''),
                        modloader=curseforge_data.get('modloader', '') or 'Unknown',
                        downloads=curseforge_data.get('downloads', 0),
                        followers=curseforge_data.get('followers', 0),
                        last_updated=datetime.now(timezone.utc),
                        is_active=True
                    )
                    created = True
                
                modpacks_found = 1
                print(f"Modpack {'created' if created else 'updated'}: {modpack.name}")
                
            else:
                raise Exception(f"Could not fetch data for project ID {project_id}: {curseforge_data.get('error', 'Unknown error')}")
        else:
            raise Exception("Please provide a valid CurseForge project ID (numbers only).")
        
        # Update task status
        task.status = 'completed'
        task.completed_at = datetime.now(timezone.utc)
        task.modpacks_found = modpacks_found
        task.save()
        
        print(f"Scraping task {task.id} completed successfully. Modpacks found: {modpacks_found}")
        
    except Exception as e:
        # Update task status on error
        task.status = 'failed'
        task.completed_at = datetime.now(timezone.utc)
        task.error_message = str(e)
        task.save()
        print(f"Scraping task {task.id} failed: {e}")


@csrf_exempt
@login_required
def api_toggle_modpack(request, modpack_id):
    """API endpoint to toggle modpack active status"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        modpack = Modpack.objects.get(id=modpack_id, is_deleted=False)
        modpack.is_active = not modpack.is_active
        modpack.save()
        
        return JsonResponse({
            'success': True,
            'is_active': modpack.is_active,
            'message': f'Modpack {"activated" if modpack.is_active else "deactivated"} successfully'
        })
        
    except Modpack.DoesNotExist:
        return JsonResponse({'error': 'Modpack not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@login_required
def api_delete_modpack(request, modpack_id):
    """API endpoint to soft delete a modpack and free up the ID for reuse"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        modpack = Modpack.objects.get(id=modpack_id, is_deleted=False)
        modpack.soft_delete()
        
        return JsonResponse({
            'success': True,
            'message': 'Modpack deleted successfully. ID is now available for reuse.'
        })
        
    except Modpack.DoesNotExist:
        return JsonResponse({'error': 'Modpack not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@login_required
def api_create_modpack(request):
    """API endpoint to create a new modpack and automatically create a scraping task"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name')
            project_id = data.get('project_id')
            
            if not name or not project_id:
                return JsonResponse({'error': 'Name and project_id are required'}, status=400)
            
            # Validate project_id is numeric
            if not str(project_id).isdigit():
                return JsonResponse({'error': 'Project ID must be a number'}, status=400)
            
            # Generate slug from name
            import re
            if not name:
                return JsonResponse({'error': 'Name is required'}, status=400)
            
            slug = re.sub(r'[^a-z0-9\s-]', '', name.lower())
            slug = re.sub(r'\s+', '-', slug)
            slug = re.sub(r'-+', '-', slug).strip('-')
            
            # Check if modpack with this slug already exists
            if Modpack.objects.filter(slug=slug, is_deleted=False).exists():
                return JsonResponse({'error': 'A modpack with this name already exists'}, status=400)
            
            # Create CurseForge URL
            curseforge_url = f"https://www.curseforge.com/minecraft/modpacks/{project_id}"
            
            # Create modpack with basic info first, reusing available ID if possible
            modpack = Modpack.create_with_reused_id(
                name=name,
                slug=slug,
                curseforge_url=curseforge_url,
                project_id=project_id,  # Store project ID
                is_active=True
            )
            
            # Create a scraping task to fetch the data
            scraping_task = ScrapingTask.objects.create(
                name=f"Fetch data for {name}",
                curseforge_url=project_id,
                status='pending'
            )
            
            # Start background update scheduler if not already running
            try:
                # Check if scheduler is already running
                if not hasattr(schedule_modpack_updates, '_running'):
                    schedule_modpack_updates._running = True
                    # Start background thread for updates
                    update_thread = threading.Thread(target=schedule_modpack_updates, daemon=True)
                    update_thread.start()
            except Exception as e:
                print(f"Error starting update scheduler: {e}")
            
            return JsonResponse({
                'success': True,
                'modpack_id': modpack.id,
                'task_id': scraping_task.id,
                'message': 'Modpack created successfully. A scraping task has been created to fetch the data.'
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
@login_required
def api_refetch_modpack(request, modpack_id):
    """API endpoint to refetch modpack data from CurseForge"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        modpack = Modpack.objects.get(id=modpack_id, is_deleted=False)
        
        # Use stored project ID or extract from URL as fallback
        project_id = modpack.project_id
        if not project_id:
            # Fallback: extract project ID from URL
            project_id_match = re.search(r'/minecraft/modpacks/(\d+)', modpack.curseforge_url)
            if not project_id_match:
                return JsonResponse({'error': 'Could not extract project ID from URL'}, status=400)
            project_id = project_id_match.group(1)
        
        # Fetch updated data from CurseForge
        curseforge_data = fetch_curseforge_data(project_id)
        
        if curseforge_data['success']:
            # Update modpack with fetched data
            if curseforge_data.get('name'):
                modpack.name = curseforge_data['name']
            if curseforge_data.get('description'):
                modpack.description = curseforge_data['description']
            if curseforge_data.get('summary'):
                modpack.summary = curseforge_data['summary']
            if curseforge_data.get('image_url'):
                modpack.image_url = curseforge_data['image_url']
            if curseforge_data.get('minecraft_version'):
                modpack.minecraft_version = curseforge_data['minecraft_version']
            if curseforge_data.get('modloader'):
                modpack.modloader = curseforge_data['modloader'] or 'Unknown'
            if curseforge_data.get('website_url'):
                modpack.curseforge_url = curseforge_data['website_url']
            if curseforge_data.get('downloads'):
                modpack.downloads = curseforge_data['downloads']
            if curseforge_data.get('followers'):
                modpack.followers = curseforge_data['followers']
            
            # Ensure project ID is stored
            modpack.project_id = project_id
            
            modpack.last_updated = datetime.now(timezone.utc)
            modpack.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Modpack "{modpack.name}" data updated successfully'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': f'Failed to fetch data: {curseforge_data.get("error", "Unknown error")}'
            }, status=400)
        
    except Modpack.DoesNotExist:
        return JsonResponse({'error': 'Modpack not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def fetch_curseforge_data(project_id):
    """Fetch modpack data from official CurseForge API"""
    try:
        # Official CurseForge API endpoint for mod data
        api_url = f"https://api.curseforge.com/v1/mods/{project_id}"
        print(f"Making request to: {api_url}")
        
        headers = {
            'Accept': 'application/json',
            'X-API-Key': '$2a$10$bL4bIL5pUWqfcO7KQtnMReakwtfHbNKh6v1uTpKlzhwoueEJQnPnm'
        }
        
        response = requests.get(api_url, headers=headers, timeout=10)
        print(f"Response status: {response.status_code}")
        response.raise_for_status()
        
        data = response.json()
        print(f"Raw API response: {data}")
        
        # Fetch description from separate endpoint
        description_url = f"https://api.curseforge.com/v1/mods/{project_id}/description"
        print(f"Making request to: {description_url}")
        
        description_response = requests.get(description_url, headers=headers, timeout=10)
        description_data = None
        if description_response.status_code == 200:
            description_data = description_response.json()
            print(f"Description API response: {description_data}")
        else:
            print(f"Description API failed with status: {description_response.status_code}")
        
        # Function to clean HTML and convert entities (for plain text)
        def clean_html_text(html_content):
            if not html_content:
                return ""
            
            import re
            from html import unescape
            
            # Remove HTML tags
            clean_text = re.sub(r'<[^>]+>', '', html_content)
            
            # Convert HTML entities
            clean_text = unescape(clean_text)
            
            # Remove extra whitespace
            clean_text = re.sub(r'\s+', ' ', clean_text)
            
            # Remove common HTML entities that might remain
            clean_text = clean_text.replace('&nbsp;', ' ')
            clean_text = clean_text.replace('&mdash;', '—')
            clean_text = clean_text.replace('&ndash;', '–')
            clean_text = clean_text.replace('&rsquo;', ''')
            clean_text = clean_text.replace('&lsquo;', ''')
            clean_text = clean_text.replace('&rdquo;', '"')
            clean_text = clean_text.replace('&ldquo;', '"')
            
            return clean_text.strip()
        
        # Function to clean HTML while preserving images and formatting
        def clean_html_preserve_formatting(html_content):
            if not html_content:
                return ""
            
            import re
            from html import unescape
            
            # Convert HTML entities
            clean_html = unescape(html_content)
            
            # Remove potentially harmful tags but keep safe ones
            # Remove script, style, iframe, object, embed tags
            clean_html = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*?</\1>', '', clean_html, flags=re.IGNORECASE | re.DOTALL)
            
            # Remove on* attributes (event handlers)
            clean_html = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', '', clean_html, flags=re.IGNORECASE)
            
            # Remove javascript: URLs
            clean_html = re.sub(r'javascript:', '', clean_html, flags=re.IGNORECASE)
            
            # Remove data: URLs (except for images)
            clean_html = re.sub(r'data:(?!image)[^;]*;base64,[^"\']*', '', clean_html, flags=re.IGNORECASE)
            
            # Clean up extra whitespace
            clean_html = re.sub(r'\s+', ' ', clean_html)
            
            return clean_html.strip()
        
        if data and isinstance(data, dict):
            # Official CurseForge API returns data directly
            actual_data = data.get('data', data)
            
            # Extract description from official API response
            raw_description = description_data.get('data') if description_data else (actual_data.get('description'))
            # Use the formatting-preserving function for description
            cleaned_description = clean_html_preserve_formatting(raw_description)
            
            result = {
                'name': actual_data.get('name'),
                'description': cleaned_description,  # Full description from /description endpoint
                'summary': actual_data.get('summary', ''),  # Short summary from main endpoint
                'image_url': None,
                'downloads': actual_data.get('downloadCount', 0),
                'followers': actual_data.get('followers', 0),
                'minecraft_version': None,
                'modloader': None,
                'website_url': None,
                'success': True
            }
            
            # Handle logo/image URL from official API
            if actual_data.get('logo'):
                if isinstance(actual_data['logo'], dict):
                    result['image_url'] = actual_data['logo'].get('url')
                elif isinstance(actual_data['logo'], str):
                    result['image_url'] = actual_data['logo']
            
            # Extract website URL from links
            if actual_data.get('links') and isinstance(actual_data['links'], dict):
                result['website_url'] = actual_data['links'].get('websiteUrl')
            
            # Extract Minecraft version and modloader from latest files
            if actual_data.get('latestFiles') and isinstance(actual_data['latestFiles'], list):
                for file_info in actual_data['latestFiles']:
                    # Try sortableGameVersions first (more reliable)
                    if file_info.get('sortableGameVersions'):
                        sortable_versions = file_info['sortableGameVersions']
                        for version_info in sortable_versions:
                            if isinstance(version_info, dict):
                                version_name = version_info.get('gameVersionName', '')
                                # Find Minecraft version (starts with 1.)
                                if version_name.startswith('1.'):
                                    result['minecraft_version'] = version_name
                                # Find modloader (Forge, NeoForge, Fabric, etc.)
                                elif version_name.lower() in ['forge', 'neoforge', 'fabric', 'quilt']:
                                    result['modloader'] = version_name
                    
                    # Fallback to gameVersions if sortableGameVersions didn't work
                    if not result['minecraft_version'] or not result['modloader']:
                        if file_info.get('gameVersions'):
                            game_versions = file_info['gameVersions']
                            # Find Minecraft version (starts with 1.)
                            for version in game_versions:
                                if version.startswith('1.'):
                                    result['minecraft_version'] = version
                                    break
                            
                            # Find modloader (Forge, NeoForge, Fabric, etc.)
                            for version in game_versions:
                                if version.lower() in ['forge', 'neoforge', 'fabric', 'quilt']:
                                    result['modloader'] = version
                                    break
                    
                    # If we found both, break
                    if result['minecraft_version'] and result['modloader']:
                        break
            
            print(f"Processed data: {result}")
            return result
        else:
            print(f"Invalid API response structure: {data}")
            return {
                'success': False,
                'error': 'Invalid API response structure'
            }
        
    except requests.exceptions.RequestException as e:
        print(f"CurseForge API request error: {e}")
        return {
            'success': False,
            'error': f'CurseForge API request error: {str(e)}'
        }
    except Exception as e:
        print(f"CurseForge API unexpected error: {e}")
        return {
            'success': False,
            'error': str(e)
        }

def update_modpack_data(modpack):
    """Update modpack data from CurseForge"""
    try:
        # Use stored project ID or extract from URL as fallback
        project_id = modpack.project_id
        if not project_id:
            # Fallback: extract project ID from URL
            project_id_match = re.search(r'/minecraft/modpacks/(\d+)', modpack.curseforge_url)
            if not project_id_match:
                return False
            project_id = project_id_match.group(1)
        
        data = fetch_curseforge_data(project_id)
        
        if data['success']:
            # Update modpack with fetched data
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
            
            # Ensure project ID is stored
            modpack.project_id = project_id
            
            modpack.last_updated = datetime.now(timezone.utc)
            modpack.save()
            return True
        else:
            return False
            
    except Exception as e:
        print(f"Error updating modpack {modpack.id}: {e}")
        return False

def schedule_modpack_updates():
    """Background task to update all modpacks every 30 minutes and run pending tasks every 5 minutes"""
    import datetime
    
    last_modpack_update = 0
    last_task_run = 0
    
    print(f"[{datetime.now(timezone.utc)}] Background scheduler started!")
    print("• Pending tasks will run every 5 minutes")
    print("• Modpack data will update every 30 minutes")
    
    while True:
        try:
            # Get current time for comparisons (in seconds since epoch)
            current_time = time.time()
            # Format current time as a string for logging (timezone-aware)
            current_time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            
            # Run pending tasks every 5 minutes
            if current_time - last_task_run >= 300:  # 5 minutes = 300 seconds
                print(f"[{current_time_str}] Running pending tasks...")
                pending_tasks = ScrapingTask.objects.filter(status='pending')
                task_count = pending_tasks.count()
                
                if task_count > 0:
                    for task in pending_tasks:
                        try:
                            print(f"[{current_time_str}] Running task {task.id}: {task.name}")
                            _run_scraping_task(task)
                            time.sleep(2)  # Small delay between tasks
                        except Exception as e:
                            print(f"[{current_time_str}] Error running task {task.id}: {e}")
                    print(f"[{current_time_str}] Completed running {task_count} pending tasks")
                else:
                    print(f"[{current_time_str}] No pending tasks to run")
                
                last_task_run = current_time
            
            # Update modpacks every 30 minutes
            if current_time - last_modpack_update >= 1800:  # 30 minutes = 1800 seconds
                print(f"[{current_time_str}] Updating modpack data...")
                modpacks = Modpack.objects.filter(is_deleted=False, is_active=True)
                modpack_count = modpacks.count()
                
                if modpack_count > 0:
                    for modpack in modpacks:
                        try:
                            print(f"[{current_time_str}] Updating modpack: {modpack.name}")
                            update_modpack_data(modpack)
                            time.sleep(1)  # Small delay between requests to be respectful
                        except Exception as e:
                            print(f"[{current_time_str}] Error updating modpack {modpack.name}: {e}")
                    print(f"[{current_time_str}] Completed updating {modpack_count} modpacks")
                else:
                    print(f"[{current_time_str}] No modpacks to update")
                
                last_modpack_update = current_time
            
            # Sleep for 1 minute before checking again
            time.sleep(60)
            
        except Exception as e:
            error_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{error_time}] Error in scheduler: {e}")
            time.sleep(300)  # Wait 5 minutes before retrying


def fetch_modpack_files(project_id):
    """Fetch modpack files from official CurseForge API"""
    try:
        # Official CurseForge API endpoint for files
        api_url = f"https://api.curseforge.com/v1/mods/{project_id}/files"
        print(f"Making request to: {api_url}")
        
        headers = {
            'Accept': 'application/json',
            'X-API-Key': '$2a$10$bL4bIL5pUWqfcO7KQtnMReakwtfHbNKh6v1uTpKlzhwoueEJQnPnm'
        }
        
        response = requests.get(api_url, headers=headers, timeout=10)
        print(f"Files API response status: {response.status_code}")
        response.raise_for_status()
        
        data = response.json()
        print(f"Files API response: {data}")
        
        if data and isinstance(data, dict):
            # Official CurseForge API returns files under 'data' key
            files_data = data.get('data', [])
            
            # Process files data
            files = []
            for file_info in files_data:
                file_data = {
                    'id': file_info.get('id'),
                    'display_name': file_info.get('displayName'),
                    'file_name': file_info.get('fileName'),
                    'file_date': file_info.get('fileDate'),
                    'file_length': file_info.get('fileLength'),
                    'download_count': file_info.get('downloadCount'),
                    'download_url': file_info.get('downloadUrl'),
                    'release_type': file_info.get('releaseType'),
                    'game_versions': file_info.get('gameVersions', []),
                    'mod_loaders': [v for v in file_info.get('gameVersions', []) if v.lower() in ['forge', 'neoforge', 'fabric', 'quilt']]
                }
                files.append(file_data)
            
            # Sort files by date (newest first)
            files.sort(key=lambda x: x['file_date'] or '', reverse=True)
            
            return {
                'success': True,
                'files': files
            }
        else:
            return {
                'success': False,
                'error': 'Invalid API response structure'
            }
        
    except requests.exceptions.RequestException as e:
        print(f"CurseForge Files API request error: {e}")
        return {
            'success': False,
            'error': f'CurseForge Files API request error: {str(e)}'
        }
    except Exception as e:
        print(f"CurseForge Files API unexpected error: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def fetch_modpack_dependencies(project_id, force_refresh=False):
    """Fetch modpack dependencies from official CurseForge API with database storage"""
    from django.core.cache import cache
    from datetime import datetime, timedelta
    
    # First, try to get from database
    try:
        modpack = Modpack.objects.get(project_id=project_id, is_deleted=False)
        stored_dependencies = modpack.dependencies.all()
        
        # Check if we have recent data (less than 24 hours old)
        if stored_dependencies.exists():
            latest_fetch = stored_dependencies.aggregate(
                models.Max('last_fetched')
            )['last_fetched__max']
            
            if latest_fetch and (django_datetime.now(timezone.utc) - latest_fetch).days < 1:
                print(f"Using stored dependencies for project {project_id}")
                dependencies_list = []
                for dep in stored_dependencies:
                    dep_data = {
                        'id': dep.mod_id,
                        'name': dep.name,
                        'slug': dep.slug,
                        'summary': dep.summary,
                        'logo_url': dep.logo_url,
                        'author': dep.author,
                        'download_count': dep.download_count,
                        'date_created': dep.date_created,
                        'date_modified': dep.date_modified,
                        'date_released': dep.date_released,
                        'website_url': dep.website_url,
                        'curseforge_url': dep.curseforge_url
                    }
                    dependencies_list.append(dep_data)
                
                return {
                    'success': True,
                    'dependencies': dependencies_list,
                    'from_database': True
                }
    except Modpack.DoesNotExist:
        pass
    
    try:
        # Official CurseForge API endpoint for dependencies
        api_url = f"https://curseforge.com/api/v1/mods/{project_id}/dependencies?index=0&pageSize=999"
        print(f"Making request to: {api_url}")
        
        headers = {
            'Accept': 'application/json',
            'X-API-Key': '$2a$10$bL4bIL5pUWqfcO7KQtnMReakwtfHbNKh6v1uTpKlzhwoueEJQnPnm'
        }
        
        response = requests.get(api_url, headers=headers, timeout=10)
        
        # If dependencies endpoint is not available, return empty list with info message
        if response.status_code == 404:
            result = {
                'success': True,
                'dependencies': [],
                'message': 'Dependencies endpoint not available in current API version'
            }
            # Cache the result for 1 hour
            cache.set(cache_key, result, 3600)
            return result
        
        response.raise_for_status()
        
        data = response.json()
        print(f"Dependencies API response: {data}")
                
        if data and isinstance(data, dict):
            # Official CurseForge API returns dependencies under 'data' key
            dependencies_data = data.get('data', [])
            
            # Process dependencies data
            dependencies = []
            for dep_info in dependencies_data:
                # Get author information
                author_name = dep_info.get('authorName', 'Unknown')
                if not author_name or author_name == 'Unknown':
                    authors = dep_info.get('authors', [])
                    author_name = authors[0].get('name') if authors else 'Unknown'
                
                # Get logo URL
                logo_url = dep_info.get('logoUrl')
                
                # Parse dates properly
                from datetime import datetime
                
                def parse_date(date_str):
                    if not date_str:
                        return None
                    try:
                        # Handle ISO format dates like "2025-08-03T18:41:52.733Z"
                        if 'T' in date_str:
                            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        else:
                            return datetime.strptime(date_str, '%Y-%m-%d')
                    except:
                        return None
                
                dep_data = {
                    'id': dep_info.get('id'),
                    'name': dep_info.get('name'),
                    'slug': dep_info.get('slug'),
                    'summary': dep_info.get('summary'),
                    'logo_url': logo_url,
                    'author': author_name,
                    'download_count': dep_info.get('downloadCount'),
                    'date_created': parse_date(dep_info.get('dateCreated')),
                    'date_modified': parse_date(dep_info.get('dateModified')),
                    'date_released': parse_date(dep_info.get('dateReleased')),
                    'website_url': dep_info.get('links', {}).get('websiteUrl') if dep_info.get('links') else None,
                    'curseforge_url': f"https://www.curseforge.com/minecraft/mc-mods/{dep_info.get('slug')}" if dep_info.get('slug') else None
                }
                dependencies.append(dep_data)
            
            # Sort dependencies by name
            dependencies.sort(key=lambda x: x['name'] or '')
            
            # Store dependencies in database
            try:
                modpack = Modpack.objects.get(project_id=project_id, is_deleted=False)
                
                # Clear existing dependencies
                modpack.dependencies.all().delete()
                
                # Create new dependency records
                for dep_data in dependencies:
                    ModDependency.objects.create(
                        modpack=modpack,
                        mod_id=dep_data['id'],
                        name=dep_data['name'],
                        slug=dep_data['slug'] or '',
                        summary=dep_data['summary'] or '',
                        logo_url=dep_data['logo_url'] or '',
                        author=dep_data['author'] or '',
                        download_count=dep_data['download_count'] or 0,
                        date_created=dep_data['date_created'],
                        date_modified=dep_data['date_modified'],
                        date_released=dep_data['date_released'],
                        website_url=dep_data['website_url'] or '',
                        curseforge_url=dep_data['curseforge_url'] or ''
                    )
                
                print(f"Stored {len(dependencies)} dependencies for project {project_id}")
                
            except Modpack.DoesNotExist:
                print(f"Modpack not found for project {project_id}")
            
            result = {
                'success': True,
                'dependencies': dependencies
            }
            
            return result
        else:
            result = {
                'success': False,
                'error': 'Invalid API response structure'
            }
            return result
        
    except requests.exceptions.RequestException as e:
        print(f"CurseForge Dependencies API request error: {e}")
        result = {
            'success': False,
            'error': f'CurseForge Dependencies API request error: {str(e)}'
        }
        return result
    except Exception as e:
        print(f"CurseForge Dependencies API unexpected error: {e}")
        result = {
            'success': False,
            'error': str(e)
        }
        return result


def modpack_dependencies(request, slug):
    """Display modpack dependencies - save API endpoints"""
    
    modpack = get_object_or_404(Modpack, slug=slug, is_deleted=False, is_active=True)
    
    # Use stored project ID or extract from URL as fallback
    project_id = modpack.project_id
    if not project_id:
        # Fallback: extract project ID from URL
        project_id_match = re.search(r'/minecraft/modpacks/(\d+)', modpack.curseforge_url)
        if not project_id_match:
            return render(request, 'modpacks/modpack_dependencies.html', {
                'modpack': modpack,
                'dependencies': [],
                'error': 'Could not extract project ID from URL'
            })
        project_id = project_id_match.group(1)
    
    # Check if force refresh is requested
    force_refresh = request.GET.get('refresh') == 'true'
    dependencies_data = fetch_modpack_dependencies(project_id, force_refresh=force_refresh)
    
    # Get modpack logo and author information
    modpack.logo_url = None
    modpack.author = None
    
    # Try to get logo and author from the modpack's stored data
    try:
        mod_data = fetch_curseforge_data(project_id)
        if mod_data['success']:
            # Get author information
            if mod_data.get('authorName'):
                modpack.author = mod_data['authorName']

            # Get logo URL - try different possible structures
            if mod_data.get('logoUrl'):
                modpack.logo_url = mod_data['logoUrl']
    except:
        pass  # If we can't fetch the data, continue without author/logo
    
    context = {
        'modpack': modpack,
        'dependencies': dependencies_data.get('dependencies', []) if dependencies_data['success'] else [],
        'error': dependencies_data.get('error') if not dependencies_data['success'] else None,
        'message': dependencies_data.get('message') if dependencies_data['success'] else None
    }
    
    # Add data source indicator
    context['data_source'] = 'Database' if dependencies_data.get('from_database') else 'API'
    
    return render(request, 'modpacks/modpack_dependencies.html', context)


def modpack_files(request, slug):
    """Display modpack files"""
    modpack = get_object_or_404(Modpack, slug=slug, is_deleted=False, is_active=True)
    
    # Use stored project ID or extract from URL as fallback
    project_id = modpack.project_id
    if not project_id:
        # Fallback: extract project ID from URL
        project_id_match = re.search(r'/minecraft/modpacks/(\d+)', modpack.curseforge_url)
        if not project_id_match:
            return render(request, 'modpacks/modpack_files.html', {
                'modpack': modpack,
                'files': [],
                'error': 'Could not extract project ID from URL'
            })
        project_id = project_id_match.group(1)
    
    files_data = fetch_modpack_files(project_id)
    
    context = {
        'modpack': modpack,
        'files': files_data.get('files', []) if files_data['success'] else [],
        'error': files_data.get('error') if not files_data['success'] else None
    }
    
    return render(request, 'modpacks/modpack_files.html', context)


@login_required
def analytics_dashboard(request):
    """Display analytics dashboard for staff"""
    if not request.user.is_staff:
        return render(request, '404.html', status=404)
    
    # Get analytics summary
    analytics_summary = SiteAnalytics.get_analytics_summary()
    
    # Get recent hits (last 10)
    recent_hits = SiteAnalytics.objects.all()[:10]
    
    context = {
        'analytics': analytics_summary,
        'recent_hits': recent_hits,
        'total_hits_count': SiteAnalytics.objects.count(),
    }
    
    return render(request, 'modpacks/analytics_dashboard.html', context)
