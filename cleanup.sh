# Stop background processes
 pkill -f "uvicorn backend.main"
 pkill -f "uvicorn ai-agent.main"
 pkill -f "npm run dev"
#
# # Stop & remove telemetry stack
 cd telemetry
 docker-compose down
 cd ..
#
# # Remove Docker network
 docker network rm telemetry
#
# # Remove virtual environments & logs
 rm -rf backend/venv ai-agent/venv
 rm -f backend.log ai-agent.log frontend.log
#
# # Remove generated user apps
 rm -rf user-apps
