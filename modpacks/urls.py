from django.urls import path
from . import views

app_name = 'modpacks'

urlpatterns = [
    path('', views.home, name='home'),
    path('modpacks/', views.modpack_list, name='modpack_list'),
    path('modpacks/<slug:slug>/', views.modpack_detail, name='modpack_detail'),
    path('modpacks/<slug:slug>/files/', views.modpack_files, name='modpack_files'),
    path('modpacks/<slug:slug>/dependencies/', views.modpack_dependencies, name='modpack_dependencies'),
    
    # Authentication
    path('login/', views.custom_login, name='custom_login'),
    path('logout/', views.custom_logout, name='custom_logout'),
    
    # Custom admin routes
    path('staff/', views.admin_dashboard, name='admin_dashboard'),
    path('staff/modpacks/', views.admin_modpacks, name='admin_modpacks'),
    path('staff/tasks/', views.admin_tasks, name='admin_tasks'),
    path('staff/analytics/', views.analytics_dashboard, name='analytics_dashboard'),

    # API endpoints
    path('api/modpacks/create/', views.api_create_modpack, name='api_create_modpack'),
    path('api/tasks/<int:task_id>/run/', views.api_run_task, name='api_run_task'),
    path('api/modpacks/<int:modpack_id>/toggle/', views.api_toggle_modpack, name='api_toggle_modpack'),
    path('api/modpacks/<int:modpack_id>/delete/', views.api_delete_modpack, name='api_delete_modpack'),
    path('api/modpacks/<int:modpack_id>/refetch/', views.api_refetch_modpack, name='api_refetch_modpack'),
] 