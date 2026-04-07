"""
Test script to create a new Telegram bot and verify database handling fixes.
This will validate that the template fixes work correctly in production.
"""
import requests
import json
import time

# Configuration
API_BASE = "http://localhost:8002"  # Your backend API
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Replace with actual bot token from @BotFather

# Test bot details
TEST_BOT = {
    "name": "test-database-fix-bot",
    "description": "Test bot to verify database optional handling",
    "user_id": 1,
    "type_id": 2,  # Telegram bot type
    "bot_token": BOT_TOKEN
}

def create_test_bot():
    """Create a new Telegram bot project."""
    print("🚀 Creating test Telegram bot...")
    print(f"   Name: {TEST_BOT['name']}")
    print(f"   Type: Telegram Bot (type_id=2)")
    
    response = requests.post(
        f"{API_BASE}/projects",
        json=TEST_BOT,
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code == 201:
        project = response.json()
        print(f"\n✅ Bot created successfully!")
        print(f"   Project ID: {project['id']}")
        print(f"   Status: {project['status']}")
        print(f"   Path: {project.get('project_path', 'N/A')}")
        return project
    else:
        print(f"\n❌ Failed to create bot")
        print(f"   Status: {response.status_code}")
        print(f"   Error: {response.text}")
        return None

def check_bot_status(project_id):
    """Check bot deployment status."""
    print(f"\n🔍 Checking bot status (Project ID: {project_id})...")
    
    max_attempts = 30
    for attempt in range(max_attempts):
        response = requests.get(f"{API_BASE}/projects/{project_id}")
        
        if response.status_code == 200:
            project = response.json()
            status = project.get('status', 'unknown')
            
            print(f"   Attempt {attempt + 1}/{max_attempts}: Status = {status}")
            
            if status == 'active':
                print(f"\n✅ Bot is now active!")
                return project
            elif status == 'error':
                print(f"\n❌ Bot deployment failed")
                print(f"   Error: {project.get('error_message', 'Unknown error')}")
                return None
            
            time.sleep(2)
        else:
            print(f"   Attempt {attempt + 1}: Failed to fetch status")
            time.sleep(2)
    
    print(f"\n⚠️ Timeout waiting for bot to become active")
    return None

def test_bot_health(project_id):
    """Test bot health endpoint."""
    print(f"\n🏥 Testing bot health endpoint...")
    
    # Get project details to find domain
    response = requests.get(f"{API_BASE}/projects/{project_id}")
    if response.status_code != 200:
        print("   ❌ Could not fetch project details")
        return False
    
    project = response.json()
    domain = project.get('domain', '')
    
    if not domain:
        print("   ⚠️ No domain found for project")
        return False
    
    health_url = f"https://{domain}.dreambigwithai.com/health"
    print(f"   Testing: {health_url}")
    
    try:
        response = requests.get(health_url, timeout=10)
        if response.status_code == 200:
            print(f"   ✅ Health check passed")
            print(f"   Response: {response.json()}")
            return True
        else:
            print(f"   ❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Health check error: {e}")
        return False

def verify_pm2_logs_ssh():
    """Print SSH command to check PM2 logs on server."""
    print("\n📋 SSH Commands to verify on server:")
    print("=" * 70)
    print("# 1. Check PM2 status")
    print("pm2 list | grep test-database-fix-bot")
    print()
    print("# 2. Check recent logs (look for proper database handling)")
    print("pm2 logs test-database-fix-bot-<id>-bot --lines 50")
    print()
    print("# 3. Expected log messages:")
    print("#    ✅ 'Bot application built successfully'")
    print("#    ✅ 'No DATABASE_URL configured - running without database'")
    print("#    ❌ Should NOT see: TypeError: 'NoneType' object is not callable")
    print("=" * 70)

def main():
    """Run the test."""
    print("=" * 70)
    print("Telegram Bot Database Fix Verification Test")
    print("=" * 70)
    
    # Step 1: Create bot
    project = create_test_bot()
    if not project:
        return
    
    project_id = project['id']
    
    # Step 2: Wait for deployment
    project = check_bot_status(project_id)
    if not project:
        print("\n⚠️ Bot deployment may still be in progress. Check server logs.")
    
    # Step 3: Test health endpoint
    test_bot_health(project_id)
    
    # Step 4: Print SSH verification commands
    verify_pm2_logs_ssh()
    
    print("\n" + "=" * 70)
    print("✅ Test complete!")
    print("=" * 70)
    print("\nNext steps:")
    print("1. SSH to your server")
    print("2. Run the PM2 commands above to verify logs")
    print("3. Send /start to your bot via Telegram")
    print("4. Verify bot responds without crashes")
    print("=" * 70)

if __name__ == "__main__":
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("⚠️ Please update BOT_TOKEN in this script first!")
        print("   Get a token from @BotFather on Telegram")
    else:
        main()
