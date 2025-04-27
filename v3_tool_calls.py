import asyncio
import json
from typing import List
from pydantic import BaseModel, Field
from agents import Agent, Runner, function_tool
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

model = os.getenv('MODEL_CHOICE', 'gpt-4o-mini')

# --- Models for structured outputs ---

class TravelPlan(BaseModel):
    destination: str
    duration_days: int
    budget: float
    activities: List[str] = Field(description="List of recommended activities")
    notes: str = Field(description="Additional notes or recommendations")

# --- Tools ---

@function_tool
def get_weather_forecast(city: str, date: str) -> str:
    """Get the weather forecast for a city on a specific date."""
    # In a real implementation, this would call a weather API
    weather_data = {
        "New York": {"sunny": 0.3, "rainy": 0.4, "cloudy": 0.3},
        "Los Angeles": {"sunny": 0.8, "rainy": 0.1, "cloudy": 0.1},
        "Chicago": {"sunny": 0.4, "rainy": 0.3, "cloudy": 0.3},
        "Miami": {"sunny": 0.7, "rainy": 0.2, "cloudy": 0.1},
        "London": {"sunny": 0.2, "rainy": 0.5, "cloudy": 0.3},
        "Paris": {"sunny": 0.4, "rainy": 0.3, "cloudy": 0.3},
        "Tokyo": {"sunny": 0.5, "rainy": 0.3, "cloudy": 0.2},
    }
    
    if city in weather_data:
        conditions = weather_data[city]
        # Simple simulation based on probabilities
        highest_prob = max(conditions, key=conditions.get)
        temp_range = {
            "New York": "15-25°C",
            "Los Angeles": "20-30°C",
            "Chicago": "10-20°C",
            "Miami": "25-35°C",
            "London": "10-18°C",
            "Paris": "12-22°C",
            "Tokyo": "15-25°C",
        }
        return f"The weather in {city} on {date} is forecasted to be {highest_prob} with temperatures around {temp_range.get(city, '15-25°C')}."
    else:
        return f"Weather forecast for {city} is not available."

# --- Main Travel Agent ---

travel_agent = Agent(
    name="Travel Planner",
    instructions="""
    You are a comprehensive travel planning assistant that helps users plan their perfect trip.
    
    You can:
    1. Provide weather information for destinations
    2. Create personalized travel itineraries
    
    Always be helpful, informative, and enthusiastic about travel. Provide specific recommendations
    based on the user's interests and preferences.
    
    When creating travel plans, consider:
    - The weather at the destination
    - Local attractions and activities
    - Budget constraints
    - Travel duration
    """,
    model=model,
    tools=[get_weather_forecast],
    output_type=TravelPlan
)

# --- Main Function ---

async def main():
    # Example queries to test the system
    queries = [
        "I'm planning a trip to Miami for 5 days with a budget of $2000. What should I do there and what is the weather going to look like?",
        "I want to visit Paris for a week with a budget of $3000. What activities do you recommend based on the weather?"
    ]
    
    for query in queries:
        print("\n" + "="*50)
        print(f"QUERY: {query}")
        
        result = await Runner.run(travel_agent, query)
        
        print("\nFINAL RESPONSE:")
        travel_plan = result.final_output
        
        # Format the output in a nicer way
        print(f"\n🌍 TRAVEL PLAN FOR {travel_plan.destination.upper()} 🌍")
        print(f"Duration: {travel_plan.duration_days} days")
        print(f"Budget: ${travel_plan.budget}")
        
        print("\n🎯 RECOMMENDED ACTIVITIES:")
        for i, activity in enumerate(travel_plan.activities, 1):
            print(f"  {i}. {activity}")
        
        print(f"\n📝 NOTES: {travel_plan.notes}")

if __name__ == "__main__":
    asyncio.run(main())