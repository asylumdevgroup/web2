from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from modpacks.models import Modpack


class Command(BaseCommand):
    help = 'Permanently delete modpacks that have been soft-deleted for more than 30 days'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to wait before permanently deleting (default: 30)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        
        cutoff_date = timezone.now() - timedelta(days=days)
        deleted_modpacks = Modpack.objects.filter(
            is_deleted=True,
            deleted_at__lt=cutoff_date
        )
        
        count = deleted_modpacks.count()
        
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS('No modpacks to permanently delete.')
            )
            return
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'Would permanently delete {count} modpacks deleted more than {days} days ago:')
            )
            for modpack in deleted_modpacks:
                self.stdout.write(f'  - {modpack.name} (ID: {modpack.id}, deleted: {modpack.deleted_at})')
        else:
            self.stdout.write(
                self.style.WARNING(f'Permanently deleting {count} modpacks deleted more than {days} days ago...')
            )
            
            for modpack in deleted_modpacks:
                self.stdout.write(f'  - Deleting {modpack.name} (ID: {modpack.id})')
                modpack.delete()
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully deleted {count} modpacks.')
            ) 