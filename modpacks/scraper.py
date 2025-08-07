import requests
import re
from urllib.parse import urlparse
from django.utils import timezone
from .models import Modpack


class CurseForgeAPI:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.base_url = "https://api.curse.tools/v1/cf"
    
    def extract_project_id_from_url(self, url):
        """Extract project ID from CurseForge URL"""
        # Handle different URL formats for single modpacks
        patterns = [
            r'/projects/([^/]+)',
            r'/minecraft/modpacks/([^/]+)',
            r'/minecraft/mc-mods/([^/]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    def get_project_data(self, project_id):
        """Get project data from CurseForge API"""
        try:
            url = f"{self.base_url}/mods/{project_id}"
            response = self.session.get(url)
            response.raise_for_status()
            
            data = response.json()
            return self._parse_project_data(data)
            
        except requests.RequestException as e:
            print(f"Error fetching project {project_id}: {str(e)}")
            return None
        except Exception as e:
            print(f"Error parsing project {project_id}: {str(e)}")
            return None
    
    def _parse_project_data(self, data):
        """Parse project data from API response"""
        try:
            modpack_data = {}
            
            # Basic information
            modpack_data['name'] = data.get('name', '')
            modpack_data['description'] = data.get('summary', '')
            modpack_data['curseforge_url'] = f"https://www.curseforge.com/minecraft/modpacks/{data.get('slug', '')}"
            
            # Generate slug from name
            if modpack_data['name']:
                modpack_data['slug'] = self._generate_slug(modpack_data['name'])
            
            # Get image
            if data.get('logo', {}).get('url'):
                modpack_data['image_url'] = data['logo']['url']
            
            # Get statistics
            stats = data.get('stats', {})
            modpack_data['downloads'] = stats.get('downloads', 0)
            modpack_data['followers'] = stats.get('followers', 0)
            
            # Get latest file information for version and modloader
            latest_file = self._get_latest_file_info(data.get('id'))
            if latest_file:
                modpack_data['minecraft_version'] = latest_file.get('game_versions', ['Unknown'])[0]
                modpack_data['modloader'] = latest_file.get('mod_loader', 'Unknown')
            
            return modpack_data
            
        except Exception as e:
            print(f"Error parsing project data: {str(e)}")
            return None
    
    def _get_latest_file_info(self, project_id):
        """Get latest file information for version and modloader"""
        try:
            url = f"{self.base_url}/mods/{project_id}/files"
            response = self.session.get(url)
            response.raise_for_status()
            
            files = response.json()
            if files and len(files) > 0:
                latest_file = files[0]  # Assuming files are sorted by date
                return latest_file
            
        except Exception as e:
            print(f"Error fetching file info for project {project_id}: {str(e)}")
        
        return None
    
    def _generate_slug(self, name):
        """Generate a URL-friendly slug from the modpack name"""
        slug = re.sub(r'[^\w\s-]', '', name.lower())
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug.strip('-')
    
    def save_modpack(self, modpack_data):
        """Save or update a modpack in the database"""
        if not modpack_data or not modpack_data.get('name'):
            return None
        
        modpack, created = Modpack.objects.update_or_create(
            slug=modpack_data['slug'],
            defaults={
                'name': modpack_data['name'],
                'curseforge_url': modpack_data['curseforge_url'],
                'description': modpack_data.get('description', ''),
                'minecraft_version': modpack_data.get('minecraft_version', ''),
                'modloader': modpack_data.get('modloader', ''),
                'image_url': modpack_data.get('image_url', ''),
                'downloads': modpack_data.get('downloads', 0),
                'followers': modpack_data.get('followers', 0),
                'last_updated': timezone.now(),
            }
        )
        
        return modpack