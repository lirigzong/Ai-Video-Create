import React, { useState, useEffect } from "react";
import "./App.css";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const VideoGenerator = () => {
  const [prompt, setPrompt] = useState("");
  const [duration, setDuration] = useState(60);
  const [segments, setSegments] = useState(3);
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentVideoId, setCurrentVideoId] = useState(null);
  const [videoStatus, setVideoStatus] = useState(null);
  const [videoList, setVideoList] = useState([]);

  // Test API connections on component mount
  useEffect(() => {
    testAPIConnections();
    loadVideoList();
  }, []);

  // Poll video status when generating
  useEffect(() => {
    if (currentVideoId && isGenerating) {
      const interval = setInterval(checkVideoStatus, 2000);
      return () => clearInterval(interval);
    }
  }, [currentVideoId, isGenerating]);

  const testAPIConnections = async () => {
    try {
      // Test basic API
      const response = await axios.get(`${API}/`);
      console.log("API Connection:", response.data.message);
      
      // Test DeepSeek
      const deepseekTest = await axios.post(`${API}/test-deepseek?prompt=Test script generation`);
      console.log("DeepSeek Test:", deepseekTest.data.status);
      
      // Test DALL-E (optional, might be slow)
      // const dalleTest = await axios.post(`${API}/test-dalle?prompt=A simple test image`);
      // console.log("DALL-E Test:", dalleTest.data.status);
      
    } catch (error) {
      console.error("API Test Error:", error);
    }
  };

  const loadVideoList = async () => {
    try {
      const response = await axios.get(`${API}/videos`);
      setVideoList(response.data);
    } catch (error) {
      console.error("Error loading videos:", error);
    }
  };

  const generateVideo = async () => {
    if (!prompt.trim()) {
      alert("Please enter a video prompt");
      return;
    }

    setIsGenerating(true);
    setVideoStatus(null);

    try {
      const response = await axios.post(`${API}/generate-video`, {
        prompt: prompt.trim(),
        duration: parseInt(duration),
        segments: parseInt(segments)
      });

      setCurrentVideoId(response.data.id);
      setVideoStatus(response.data);
    } catch (error) {
      console.error("Error generating video:", error);
      alert("Failed to start video generation");
      setIsGenerating(false);
    }
  };

  const checkVideoStatus = async () => {
    if (!currentVideoId) return;

    try {
      const response = await axios.get(`${API}/video-status/${currentVideoId}`);
      setVideoStatus(response.data);

      if (response.data.status === "completed") {
        setIsGenerating(false);
        loadVideoList(); // Refresh video list
      } else if (response.data.status === "failed") {
        setIsGenerating(false);
        alert("Video generation failed: " + (response.data.error || "Unknown error"));
      }
    } catch (error) {
      console.error("Error checking video status:", error);
    }
  };

  const getStatusMessage = (status) => {
    switch (status) {
      case "processing":
        return "🚀 Starting video generation...";
      case "generating_script":
        return "📝 Creating script with AI...";
      case "generating_assets":
        return "🎨 Generating images and voiceover...";
      case "creating_video":
        return "🎬 Assembling final video...";
      case "completed":
        return "✅ Video generation completed!";
      case "failed":
        return "❌ Video generation failed";
      default:
        return "⏳ Processing...";
    }
  };

  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-5xl font-bold text-white mb-4">
            🎬 AI Video Generator
          </h1>
          <p className="text-xl text-gray-300 max-w-2xl mx-auto">
            Transform your ideas into engaging videos using AI-powered script generation, 
            image creation, and voice synthesis
          </p>
        </div>

        {/* Main Content */}
        <div className="max-w-4xl mx-auto">
          {/* Video Generation Form */}
          <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8 mb-8 border border-white/20">
            <h2 className="text-2xl font-bold text-white mb-6">Create Your Video</h2>
            
            <div className="space-y-6">
              <div>
                <label className="block text-white font-medium mb-2">
                  Video Prompt
                </label>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="E.g., 'Give me 5 daily beauty tips' or 'Explain how to start a garden'"
                  className="w-full px-4 py-3 rounded-lg bg-white/20 border border-white/30 text-white placeholder-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-400"
                  rows={3}
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-white font-medium mb-2">
                    Duration (seconds)
                  </label>
                  <input
                    type="number"
                    min="10"
                    max="600"
                    value={duration}
                    onChange={(e) => setDuration(e.target.value)}
                    className="w-full px-4 py-3 rounded-lg bg-white/20 border border-white/30 text-white focus:outline-none focus:ring-2 focus:ring-blue-400"
                  />
                  <p className="text-gray-300 text-sm mt-1">
                    {formatDuration(parseInt(duration))} total
                  </p>
                </div>

                <div>
                  <label className="block text-white font-medium mb-2">
                    Number of Segments
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="10"
                    value={segments}
                    onChange={(e) => setSegments(e.target.value)}
                    className="w-full px-4 py-3 rounded-lg bg-white/20 border border-white/30 text-white focus:outline-none focus:ring-2 focus:ring-blue-400"
                  />
                  <p className="text-gray-300 text-sm mt-1">
                    ~{formatDuration(Math.floor(duration / segments))} per segment
                  </p>
                </div>
              </div>

              <button
                onClick={generateVideo}
                disabled={isGenerating || !prompt.trim()}
                className="w-full py-4 px-6 bg-gradient-to-r from-blue-500 to-purple-600 text-white font-bold rounded-lg hover:from-blue-600 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 transform hover:scale-105"
              >
                {isGenerating ? (
                  <span className="flex items-center justify-center">
                    <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Generating Video...
                  </span>
                ) : (
                  "🚀 Generate Video"
                )}
              </button>
            </div>
          </div>

          {/* Generation Status */}
          {videoStatus && (
            <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-6 mb-8 border border-white/20">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xl font-bold text-white">Generation Progress</h3>
                <span className="text-gray-300 text-sm">ID: {videoStatus.id}</span>
              </div>
              
              <div className="mb-4">
                <p className="text-white text-lg">{getStatusMessage(videoStatus.status)}</p>
                {videoStatus.status !== "completed" && videoStatus.status !== "failed" && (
                  <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
                    <div className="bg-gradient-to-r from-blue-500 to-purple-600 h-2 rounded-full animate-pulse" style={{
                      width: videoStatus.status === "processing" ? "10%" :
                            videoStatus.status === "generating_script" ? "25%" :
                            videoStatus.status === "generating_assets" ? "60%" :
                            videoStatus.status === "creating_video" ? "90%" : "0%"
                    }}></div>
                  </div>
                )}
              </div>

              {videoStatus.status === "completed" && videoStatus.video_url && (
                <div className="mt-4">
                  <video
                    controls
                    className="w-full rounded-lg"
                    src={`${BACKEND_URL}${videoStatus.video_url}`}
                  >
                    Your browser does not support the video tag.
                  </video>
                  <a
                    href={`${BACKEND_URL}${videoStatus.video_url}`}
                    download
                    className="inline-block mt-3 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
                  >
                    📥 Download Video
                  </a>
                </div>
              )}

              {videoStatus.script && (
                <div className="mt-4">
                  <h4 className="text-white font-bold mb-2">Generated Script:</h4>
                  <div className="space-y-2">
                    {videoStatus.script.segments.map((segment) => (
                      <div key={segment.segment_id} className="bg-white/10 rounded-lg p-3">
                        <p className="text-blue-300 font-medium">Segment {segment.segment_id}</p>
                        <p className="text-white text-sm">{segment.content}</p>
                        <p className="text-gray-400 text-xs mt-1">Image: {segment.image_prompt}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Video Library */}
          <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-6 border border-white/20">
            <h3 className="text-xl font-bold text-white mb-4">📚 Video Library</h3>
            
            {videoList.length === 0 ? (
              <p className="text-gray-300">No videos generated yet. Create your first video above!</p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {videoList.map((video) => (
                  <div key={video.id} className="bg-white/10 rounded-lg p-4 border border-white/20">
                    <div className="mb-2">
                      <p className="text-white font-medium truncate">{video.prompt}</p>
                      <p className="text-gray-400 text-sm">
                        {formatDuration(video.duration)} • {video.segments} segments
                      </p>
                    </div>
                    
                    <div className="flex items-center justify-between">
                      <span className={`px-2 py-1 rounded text-xs ${
                        video.status === "completed" ? "bg-green-600 text-white" :
                        video.status === "failed" ? "bg-red-600 text-white" :
                        "bg-yellow-600 text-white"
                      }`}>
                        {video.status}
                      </span>
                      
                      {video.status === "completed" && video.video_url && (
                        <a
                          href={`${BACKEND_URL}${video.video_url}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-400 hover:text-blue-300 text-sm"
                        >
                          👁️ View
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

function App() {
  return (
    <div className="App">
      <VideoGenerator />
    </div>
  );
}

export default App;
