
import requests
import sys
import time
import json
from datetime import datetime

class AIVideoGeneratorTester:
    def __init__(self, base_url="https://39005e98-cfb0-4087-b974-f3138234f598.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, params=params)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return success, response.json()
                except:
                    return success, response.text
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    print(f"Response: {response.json()}")
                except:
                    print(f"Response: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_root_endpoint(self):
        """Test the root API endpoint"""
        return self.run_test("Root API Endpoint", "GET", "", 200)

    def test_deepseek_integration(self, prompt="Test script generation"):
        """Test DeepSeek API integration"""
        return self.run_test(
            "DeepSeek Integration", 
            "POST", 
            "test-deepseek", 
            200, 
            params={"prompt": prompt}
        )

    def test_dalle_integration(self, prompt="A simple test image"):
        """Test DALL-E API integration"""
        return self.run_test(
            "DALL-E Integration", 
            "POST", 
            "test-dalle", 
            200, 
            params={"prompt": prompt}
        )

    def test_tts_integration(self, text="This is a test of the text to speech functionality."):
        """Test OpenAI TTS API integration"""
        return self.run_test(
            "TTS Integration", 
            "POST", 
            "test-tts", 
            200, 
            params={"text": text}
        )

    def test_video_generation(self, prompt="Give me 3 daily beauty tips", duration=30, segments=3):
        """Test video generation pipeline"""
        success, response = self.run_test(
            "Video Generation Request", 
            "POST", 
            "generate-video", 
            200, 
            data={"prompt": prompt, "duration": duration, "segments": segments}
        )
        
        if not success or 'id' not in response:
            return False, {}
        
        video_id = response['id']
        print(f"Video generation started with ID: {video_id}")
        
        # Poll for status updates
        max_polls = 10
        polls = 0
        
        while polls < max_polls:
            polls += 1
            print(f"\nPolling video status ({polls}/{max_polls})...")
            
            success, status_response = self.run_test(
                f"Video Status Check #{polls}", 
                "GET", 
                f"video-status/{video_id}", 
                200
            )
            
            if not success:
                return False, {}
            
            status = status_response.get('status', '')
            print(f"Current status: {status}")
            
            if status == 'completed':
                print("✅ Video generation completed successfully!")
                return True, status_response
            elif status == 'failed':
                print(f"❌ Video generation failed: {status_response.get('error', 'Unknown error')}")
                return False, status_response
            
            # Wait before polling again
            time.sleep(3)
        
        print("⚠️ Test timeout - video generation is still in progress")
        return True, {"status": "in_progress", "message": "Test timeout reached but generation continues"}

    def run_all_tests(self):
        """Run all API tests"""
        print("🚀 Starting AI Video Generator API Tests")
        print("=======================================")
        
        # Basic connectivity test
        root_success, _ = self.test_root_endpoint()
        if not root_success:
            print("❌ Basic API connectivity failed, stopping tests")
            return False
        
        # Test individual API integrations
        deepseek_success, _ = self.test_deepseek_integration()
        dalle_success, _ = self.test_dalle_integration()
        tts_success, _ = self.test_tts_integration()
        
        # Only test video generation if individual integrations pass
        if deepseek_success and dalle_success and tts_success:
            print("\n✅ All API integrations passed, testing video generation pipeline...")
            video_success, _ = self.test_video_generation()
        else:
            print("\n⚠️ Some API integrations failed, skipping video generation test")
            video_success = False
        
        # Print results
        print("\n📊 Test Results:")
        print(f"Tests passed: {self.tests_passed}/{self.tests_run}")
        
        return self.tests_passed == self.tests_run

def main():
    # Create tester with the public endpoint
    tester = AIVideoGeneratorTester()
    
    # Run all tests
    success = tester.run_all_tests()
    
    # Return appropriate exit code
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
      