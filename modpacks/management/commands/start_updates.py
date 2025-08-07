from django.core.management.base import BaseCommand
from modpacks.views import schedule_modpack_updates
import threading
import time

class Command(BaseCommand):
    help = 'Start the background modpack update and task scheduler'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Starting background scheduler...')
        )
        
        # Start the background update scheduler
        update_thread = threading.Thread(target=schedule_modpack_updates, daemon=True)
        update_thread.start()
        
        self.stdout.write(
            self.style.SUCCESS('Background scheduler started successfully!')
        )
        self.stdout.write(
            self.style.WARNING('• Pending tasks will run every 5 minutes')
        )
        self.stdout.write(
            self.style.WARNING('• Modpack data will update every 30 minutes')
        )
        
        # Keep the command running
        try:
            while True:
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.SUCCESS('Stopping background scheduler...')
            ) 