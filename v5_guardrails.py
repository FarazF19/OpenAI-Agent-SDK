import asyncio
import json
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional
from pydantic import BaseModel, Field
from agents import Agent, RunContextWrapper, Runner, function_tool, ModelSettings, InputGuardrail, GuardrailFunctionOutput, InputGuardrailTripwireTriggered
from dotenv import load_dotenv
import logfire
import os

# Load environment variables
load_dotenv()

# Comment these lines out if you don't want Logfire tracing
logfire.configure(send_to_logfire='if-token-present')
logfire.instrument_openai_agents()

model = os.getenv('MODEL_CHOICE', 'gpt-4o-mini')

# --- Models for structured outputs ---

class FlightRecommendation(BaseModel):
    airline: str
    departure_time: str
    arrival_time: str
    price: float
    direct_flight: bool
    recommendation_reason: str

class HotelRecommendation(BaseModel):
    name: str
    location: str
    price_per_night: float
    amenities: List[str]
    recommendation_reason: str

class TravelPlan(BaseModel):
    destination: str
    duration_days: int
    budget: float
    activities: List[str] = Field(description="List of recommended activities")
    notes: str = Field(description="Additional notes or recommendations")

class BudgetAnalysis(BaseModel):
    is_realistic: bool
    reasoning: str
    suggested_budget: Optional[float] = None

# --- Context Class ---

@dataclass
class UserContext:  
    user_id: str
    preferred_airlines: List[str] = None
    hotel_amenities: List[str] = None
    budget_level: str = None
    session_start: datetime = None
    
    def __post_init__(self):
        if self.preferred_airlines is None:
            self.preferred_airlines = []
        if self.hotel_amenities is None:
            self.hotel_amenities = []
        if self.session_start is None:
            self.session_start = datetime.now()

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

@function_tool
async def search_flights(wrapper: RunContextWrapper[UserContext], origin: str, destination: str, date: str) -> str:
    """Search for flights between two cities on a specific date, taking user preferences into account."""
    # In a real implementation, this would call a flight search API
    flight_options = [
        {
            "airline": "SkyWays",
            "departure_time": "08:00",
            "arrival_time": "10:30",
            "price": 350.00,
            "direct": True
        },
        {
            "airline": "OceanAir",
            "departure_time": "12:45",
            "arrival_time": "15:15",
            "price": 275.50,
            "direct": True
        },
        {
            "airline": "MountainJet",
            "departure_time": "16:30",
            "arrival_time": "21:45",
            "price": 225.75,
            "direct": False
        }
    ]
    
    # Apply user preferences if available
    if wrapper and wrapper.context:
        preferred_airlines = wrapper.context.preferred_airlines
        if preferred_airlines:
            # Move preferred airlines to the top of the list
            flight_options.sort(key=lambda x: x["airline"] not in preferred_airlines)
            
            # Add a note about preference matching
            for flight in flight_options:
                if flight["airline"] in preferred_airlines:
                    flight["preferred"] = True                      
    
    return json.dumps(flight_options)

@function_tool
async def search_hotels(wrapper: RunContextWrapper[UserContext], city: str, check_in: str, check_out: str, max_price: Optional[float] = None) -> str:
    """Search for hotels in a city for specific dates within a price range, taking user preferences into account."""
    # In a real implementation, this would call a hotel search API
    hotel_options = [
        {
            "name": "City Center Hotel",
            "location": "Downtown",
            "price_per_night": 199.99,
            "amenities": ["WiFi", "Pool", "Gym", "Restaurant"]
        },
        {
            "name": "Riverside Inn",
            "location": "Riverside District",
            "price_per_night": 149.50,
            "amenities": ["WiFi", "Free Breakfast", "Parking"]
        },
        {
            "name": "Luxury Palace",
            "location": "Historic District",
            "price_per_night": 349.99,
            "amenities": ["WiFi", "Pool", "Spa", "Fine Dining", "Concierge"]
        }
    ]
    
    # Filter by max price if provided
    if max_price is not None:
        filtered_hotels = [hotel for hotel in hotel_options if hotel["price_per_night"] <= max_price]
    else:
        filtered_hotels = hotel_options
    
    # Apply user preferences if available
    if wrapper and wrapper.context:
        preferred_amenities = wrapper.context.hotel_amenities
        budget_level = wrapper.context.budget_level
        
        # Sort hotels by preference match
        if preferred_amenities:
            # Calculate a score based on how many preferred amenities each hotel has
            for hotel in filtered_hotels:
                matching_amenities = [a for a in hotel["amenities"] if a in preferred_amenities]
                hotel["matching_amenities"] = matching_amenities
                hotel["preference_score"] = len(matching_amenities)
            
            # Sort by preference score (higher scores first)
            filtered_hotels.sort(key=lambda x: x["preference_score"], reverse=True)
        
        # Apply budget level preferences if available
        if budget_level:
            if budget_level == "budget":
                filtered_hotels.sort(key=lambda x: x["price_per_night"])
            elif budget_level == "luxury":
                filtered_hotels.sort(key=lambda x: x["price_per_night"], reverse=True)
            # mid-range is already handled by the max_price filter
        
    return json.dumps(filtered_hotels)

# --- Guardrails ---

budget_analysis_agent = Agent(
    name="Budget Analyzer",
    instructions="""
    You analyze travel budgets to determine if they are realistic for the destination and duration.
    Consider factors like:
    - Average hotel costs in the destination
    - Flight costs
    - Food and entertainment expenses
    - Local transportation
    
    Provide a clear analysis of whether the budget is realistic and why.
    If the budget is not realistic, suggest a more appropriate budget.
    Don't be harsh at all, lean towards it being realistic unless it's really crazy.
    If no budget was mentioned, just assume it is realistic.
    """,
    output_type=BudgetAnalysis,
    model=model
)

async def budget_guardrail(ctx, agent, input_data):
    """Check if the user's travel budget is realistic."""
    # Parse the input to extract destination, duration, and budget
    try:
        analysis_prompt = f"The user is planning a trip and said: {input_data}.\nAnalyze if their budget is realistic for a trip to their destination for the length they mentioned."
        result = await Runner.run(budget_analysis_agent, analysis_prompt, context=ctx.context)
        final_output = result.final_output_as(BudgetAnalysis)

        if not final_output.is_realistic:
            print(f"Your budget for your trip may not be realistic. {final_output.reasoning}" if not final_output.is_realistic else None)
        
        return GuardrailFunctionOutput(
            output_info=final_output,
            tripwire_triggered=not final_output.is_realistic,
        )
    except Exception as e:
        # Handle any errors gracefully
        return GuardrailFunctionOutput(
            output_info=BudgetAnalysis(is_realistic=True, reasoning=f"Error analyzing budget: {str(e)}"),
            tripwire_triggered=False
        )

# --- Specialized Agents ---

flight_agent = Agent[UserContext](
    name="Flight Specialist",
    handoff_description="Specialist agent for finding and recommending flights",
    instructions="""
    You are a flight specialist who helps users find the best flights for their trips.
    
    Use the search_flights tool to find flight options, and then provide personalized recommendations
    based on the user's preferences (price, time, direct vs. connecting).
    
    The user's preferences are available in the context, including preferred airlines.
    
    Always explain the reasoning behind your recommendations.
    
    Format your response in a clear, organized way with flight details and prices.
    """,
    model=model,
    tools=[search_flights],
    output_type=FlightRecommendation
)

hotel_agent = Agent[UserContext](
    name="Hotel Specialist",
    handoff_description="Specialist agent for finding and recommending hotels and accommodations",
    instructions="""
    You are a hotel specialist who helps users find the best accommodations for their trips.
    
    Use the search_hotels tool to find hotel options, and then provide personalized recommendations
    based on the user's preferences (location, amenities, price range).
    
    The user's preferences are available in the context, including preferred amenities and budget level.
    
    Always explain the reasoning behind your recommendations.
    
    Format your response in a clear, organized way with hotel details, amenities, and prices.
    """,
    model=model,
    tools=[search_hotels],
    output_type=HotelRecommendation
)

conversational_agent = Agent[UserContext](
    name="General Conversation Specialist",
    handoff_description="Specialist agent for giving basic responses to the user to carry out a normal conversation as opposed to structured output.",
    instructions="""
    You are a trip planning expert who answers basic user questions about their trip and offers any suggestions.
    Act as a helpful assistant and be helpful in any way you can be.
    """,
    model=model
)

# --- Main Travel Agent ---

travel_agent = Agent[UserContext](
    name="Travel Planner",
    instructions="""
    You are a travel planning assistant who helps users plan their trips.
    
    You can provide personalized travel recommendations based on the user's destination, duration, budget, and preferences.
    
    The user's preferences are available in the context, which you can use to tailor your recommendations.
    
    You can:
    1. Get weather forecasts for destinations
    2. Hand off to specialized agents for flight and hotel recommendations
    3. Create comprehensive travel plans with activities and notes
    
    Always be helpful, informative, and enthusiastic about travel.
    """,
    model=model,
    tools=[get_weather_forecast],
    handoffs=[flight_agent, hotel_agent, conversational_agent],
    input_guardrails=[
        InputGuardrail(guardrail_function=budget_guardrail),
    ],
    output_type=TravelPlan
)

# --- Main Function ---

async def main():
    # Create a user context with some preferences
    user_context = UserContext(
        user_id="user123",
        preferred_airlines=["SkyWays", "OceanAir"],
        hotel_amenities=["WiFi", "Pool"],
        budget_level="mid-range"
    )
    
    # Example queries to test different aspects of the system
    queries = [
        "I'm planning a trip to Miami for 5 days with a budget of $2000. What should I do there?",
        "I'm planning a trip to Tokyo for a week, looking to spend under $5,000. Suggestions?",
        "I need a flight from New York to Chicago tomorrow",
        "Find me a hotel in Paris with a pool for under $400 per night",
        "I want to go to Dubai for a week with only $300"  # This should trigger the budget guardrail
    ]
    
    for query in queries:
        print("\n" + "="*50)
        print(f"QUERY: {query}")
        print("="*50)
        
        try:
            result = await Runner.run(travel_agent, query, context=user_context)
            
            print("\nFINAL RESPONSE:")
            
            # Format the output based on the type of response
            if hasattr(result.final_output, "airline"):  # Flight recommendation
                flight = result.final_output
                print("\n✈️ FLIGHT RECOMMENDATION ✈️")
                print(f"Airline: {flight.airline}")
                print(f"Departure: {flight.departure_time}")
                print(f"Arrival: {flight.arrival_time}")
                print(f"Price: ${flight.price}")
                print(f"Direct Flight: {'Yes' if flight.direct_flight else 'No'}")
                print(f"\nWhy this flight: {flight.recommendation_reason}")
                
                # Show user preferences that influenced this recommendation
                airlines = user_context.preferred_airlines
                if airlines and flight.airline in airlines:
                    print(f"\n👤 NOTE: This matches your preferred airline: {flight.airline}")
                
            elif hasattr(result.final_output, "name") and hasattr(result.final_output, "amenities"):  # Hotel recommendation
                hotel = result.final_output
                print("\n🏨 HOTEL RECOMMENDATION 🏨")
                print(f"Name: {hotel.name}")
                print(f"Location: {hotel.location}")
                print(f"Price per night: ${hotel.price_per_night}")
                
                print("\nAmenities:")
                for i, amenity in enumerate(hotel.amenities, 1):
                    print(f"  {i}. {amenity}")
                
                # Highlight matching amenities from user preferences
                preferred_amenities = user_context.hotel_amenities
                if preferred_amenities:
                    matching = [a for a in hotel.amenities if a in preferred_amenities]
                    if matching:
                        print("\n👤 MATCHING PREFERRED AMENITIES:")
                        for amenity in matching:
                            print(f"  ✓ {amenity}")
                
                print(f"\nWhy this hotel: {hotel.recommendation_reason}")
                
            elif hasattr(result.final_output, "destination"):  # Travel plan
                travel_plan = result.final_output
                print(f"\n🌍 TRAVEL PLAN FOR {travel_plan.destination.upper()} 🌍")
                print(f"Duration: {travel_plan.duration_days} days")
                print(f"Budget: ${travel_plan.budget}")
                
                # Show budget level context
                budget_level = user_context.budget_level
                if budget_level:
                    print(f"Budget Category: {budget_level.title()}")
                
                print("\n🎯 RECOMMENDED ACTIVITIES:")
                for i, activity in enumerate(travel_plan.activities, 1):
                    print(f"  {i}. {activity}")
                
                print(f"\n📝 NOTES: {travel_plan.notes}")
            
            else:  # Generic response
                print(result.final_output)
                
        except InputGuardrailTripwireTriggered as e:
            print("\n⚠️ GUARDRAIL TRIGGERED ⚠️")

if __name__ == "__main__":
    asyncio.run(main())