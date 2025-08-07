from django.core.management.base import BaseCommand
from modpacks.models import ScrapingTask
from modpacks.views import _run_scraping_task


class Command(BaseCommand):
    help = 'Run all pending scraping tasks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--task-id',
            type=int,
            help='Run a specific task by ID'
        )

    def handle(self, *args, **options):
        task_id = options.get('task_id')
        
        if task_id:
            # Run specific task
            try:
                task = ScrapingTask.objects.get(id=task_id)
                self.stdout.write(f'Running task {task_id}: {task.name}')
                _run_scraping_task(task)
                self.stdout.write(
                    self.style.SUCCESS(f'Task {task_id} completed with status: {task.status}')
                )
            except ScrapingTask.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Task {task_id} not found')
                )
        else:
            # Run all pending tasks
            pending_tasks = ScrapingTask.objects.filter(status='pending')
            count = pending_tasks.count()
            
            if count == 0:
                self.stdout.write(
                    self.style.SUCCESS('No pending tasks to run.')
                )
                return
            
            self.stdout.write(f'Running {count} pending tasks...')
            
            for task in pending_tasks:
                self.stdout.write(f'Running task {task.id}: {task.name}')
                _run_scraping_task(task)
                self.stdout.write(
                    self.style.SUCCESS(f'Task {task.id} completed with status: {task.status}')
                )
            
            self.stdout.write(
                self.style.SUCCESS(f'Completed running {count} tasks.')
            ) 