#!/bin/bash
# infrastructure/update_application.sh - Update EMR Serverless app with custom image

source "$(dirname "$0")/env_discovery.sh"

if [ -z "$APP_ID" ]; then
    echo "❌ No application ID found. Please create an application first."
    exit 1
fi

echo "🔄 Updating EMR Serverless Application: $APP_ID"
echo "📦 Custom Image: $IMAGE_URI"

# Check current application state
APP_STATE=$(aws emr-serverless get-application --application-id "$APP_ID" --query 'application.state' --output text)
echo "ℹ️  Current application state: $APP_STATE"

# Stop the application if it's running
if [ "$APP_STATE" == "STARTED" ]; then
    echo "⏸️  Stopping application..."
    aws emr-serverless stop-application --application-id "$APP_ID"

    # Wait for application to stop
    echo "⏳ Waiting for application to stop..."
    while true; do
        APP_STATE=$(aws emr-serverless get-application --application-id "$APP_ID" --query 'application.state' --output text)
        if [ "$APP_STATE" == "STOPPED" ]; then
            echo "✅ Application stopped"
            break
        fi
        echo "   Current state: $APP_STATE"
        sleep 5
    done
fi

# Update the application with custom image
echo "🔄 Updating application with custom image..."
aws emr-serverless update-application \
  --application-id "$APP_ID" \
  --image-configuration "{
    \"imageUri\": \"${IMAGE_URI}\"
  }"

if [ $? -eq 0 ]; then
    echo "✅ Application updated successfully with custom image!"
    echo "ℹ️  Application ID: $APP_ID"
    echo "ℹ️  Image URI: $IMAGE_URI"

    # Restart the application
    echo "▶️  Starting application..."
    aws emr-serverless start-application --application-id "$APP_ID"

    echo "⏳ Waiting for application to start..."
    while true; do
        APP_STATE=$(aws emr-serverless get-application --application-id "$APP_ID" --query 'application.state' --output text)
        if [ "$APP_STATE" == "STARTED" ]; then
            echo "✅ Application started and ready!"
            break
        fi
        echo "   Current state: $APP_STATE"
        sleep 5
    done
else
    echo "❌ Failed to update application"
    exit 1
fi
