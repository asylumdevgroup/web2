#!/bin/bash

# AsylumSite Startup Script
# This script starts the Django development server and background scheduler

echo "🚀 Starting AsylumSite..."

# --- Kill existing processes ---
echo "Stopping existing processes..."

pkill -f "gunicorn" 2>/dev/null
pkill -f "python3" 2>/dev/null

# Wait a moment for processes to stop
sleep 2

# --- Git operations ---
echo "Updating from git..."
git pull

# Check if git pull was successful
if [ $? -ne 0 ]; then
    echo "Git pull failed. Exiting startup script." >&2
    exit 1
fi

echo "Git pull successful"

# --- Set paths ---
PYTHON_PATH="python3"
MANAGE_PY="./manage.py"

# --- Apply migrations ---
echo "Applying database migrations..."
"$PYTHON_PATH" "$MANAGE_PY" migrate

if [ $? -ne 0 ]; then
    echo "Migration failed. Exiting startup script." >&2
    exit 1
fi

echo "Migrations applied successfully"

# --- Collect static files ---
echo "Collecting static files..."
"$PYTHON_PATH" "$MANAGE_PY" collectstatic --noinput

if [ $? -ne 0 ]; then
    echo "Static file collection failed. Exiting startup script." >&2
    exit 1
fi

echo "Static files collected"

# --- Start background scheduler ---
echo "Starting background scheduler..."
nohup "$PYTHON_PATH" "$MANAGE_PY" start_updates >> scheduler.log 2>&1 &

# Get the PID of the background scheduler
SCHEDULER_PID=$!
echo "Background scheduler started with PID: $SCHEDULER_PID"

# Wait a moment for scheduler to initialize
sleep 3

# --- Start Django development server ---
echo "Starting Django development server..."
nohup "$PYTHON_PATH" "$MANAGE_PY" runserver 0.0.0.0:8005 >> django.log 2>&1 &

# Get the PID of the Django server
DJANGO_PID=$!
echo "Django server started with PID: $DJANGO_PID"

# --- Display status ---
echo ""
echo "AsylumSite startup complete!"
echo "=================================="
echo "Services Status:"
echo "• Django Server: PID $DJANGO_PID (http://localhost:8005)"
echo "• Background Scheduler: PID $SCHEDULER_PID"
echo ""
echo "Scheduler Configuration:"
echo "• Pending tasks: Every 5 minutes"
echo "• Modpack updates: Every 30 minutes"
echo ""
echo "Log Files:"
echo "• Django server: django.log"
echo "• Background scheduler: scheduler.log"
echo ""
echo "----------------------------------"