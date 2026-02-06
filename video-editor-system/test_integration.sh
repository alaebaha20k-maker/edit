#!/bin/bash
echo "🔍 INTEGRATION TEST - Frontend + Backend + Settings"
echo ""

# Check if server is running
echo "1️⃣ Checking if Flask server is running..."
if curl -s http://localhost:5000 > /dev/null 2>&1; then
    echo "   ✅ Server is running on localhost:5000"
else
    echo "   ❌ Server NOT running! Start with: python backend/api.py"
    exit 1
fi

# Check main page
echo ""
echo "2️⃣ Checking main page (index.html)..."
if curl -s http://localhost:5000 | grep -q "Advanced Settings"; then
    echo "   ✅ Main page has 'Advanced Settings' button"
else
    echo "   ❌ Main page missing 'Advanced Settings' button"
fi

# Check settings page
echo ""
echo "3️⃣ Checking settings page (settings.html)..."
if curl -s http://localhost:5000/settings.html | grep -q "Director Gemini API Key"; then
    echo "   ✅ Settings page has 'Director Gemini API Key' field"
else
    echo "   ❌ Settings page missing 'Director Gemini API Key' field"
fi

# Check Image Styles tab
if curl -s http://localhost:5000/settings.html | grep -q "image-styles"; then
    echo "   ✅ Settings page has 'Image Styles' tab"
else
    echo "   ❌ Settings page missing 'Image Styles' tab"
fi

# Check backend API endpoints
echo ""
echo "4️⃣ Checking backend API endpoints..."
if curl -s http://localhost:5000/api/settings | grep -q "director_gemini"; then
    echo "   ✅ Backend API supports director_gemini"
else
    echo "   ❌ Backend API missing director_gemini support"
fi

if curl -s http://localhost:5000/api/auto-images/styles | grep -q "styles"; then
    echo "   ✅ Backend API supports auto-images styles"
else
    echo "   ❌ Backend API missing auto-images styles support"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ INTEGRATION TEST COMPLETE!"
echo ""
echo "📍 Access your app:"
echo "   Main App: http://localhost:5000"
echo "   Advanced Settings: http://localhost:5000/settings.html"
echo ""
echo "🎯 To add Director Gemini key:"
echo "   1. Click '🎛️ Advanced Settings' button"
echo "   2. Go to '🔑 API Keys' tab"
echo "   3. Find '🎬 Director Gemini API Key'"
echo "   4. Enter your separate Gemini API key"
echo "   5. Click '💾 Save API Keys'"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
