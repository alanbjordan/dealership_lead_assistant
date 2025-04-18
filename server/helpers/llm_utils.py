# server/helpers/llm_utils.py

from database import db
from models.sql_models import CarInventory, ConversationSummary, AutoLeadInteractionDetails
import json
import uuid
from openai import OpenAI
from helpers.token_utils import calculate_token_cost
from services.analytics_service import store_request_analytics
import os

# Initialize the OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def fetch_cars(filter_params: dict) -> list:
    """
    Query the CarInventory table based on provided filter criteria.
    
    If the user does not provide a parameter or provides -1 for numeric fields,
    the function will skip applying that filter.
    
    :param filter_params: A dictionary with keys such as:
        {
            "make": <str>,         # Car manufacturer (non-empty string to filter)
            "model": <str>,        # Car model (non-empty string to filter)
            "year": <int>,         # Minimum car model year (-1 means no filtering)
            "max_year": <int>,     # Maximum car model year (-1 means no filtering)
            "price": <float>,      # Minimum price (-1 means no filtering)
            "max_price": <float>,  # Maximum price (-1 means no filtering)
            "mileage": <int>,      # Maximum mileage (-1 means no filtering)
            "color": <str>,        # Car color (non-empty string to filter)
            "stock_number": <str>, # Exact stock number (non-empty string to filter)
            "vin": <str>           # Exact vehicle identification number (non-empty string to filter)
        }
    :return: A list of dictionaries, each representing a car in the inventory.
    """
    query = db.session.query(CarInventory)
    
    # Check string filters only if they are non-empty
    if "make" in filter_params and filter_params["make"]:
        query = query.filter(CarInventory.make.ilike(f"%{filter_params['make']}%"))
    if "model" in filter_params and filter_params["model"]:
        query = query.filter(CarInventory.model.ilike(f"%{filter_params['model']}%"))
    if "color" in filter_params and filter_params["color"]:
        query = query.filter(CarInventory.color.ilike(f"%{filter_params['color']}%"))
    if "stock_number" in filter_params and filter_params["stock_number"]:
        query = query.filter(CarInventory.stock_number == filter_params["stock_number"])
    if "vin" in filter_params and filter_params["vin"]:
        query = query.filter(CarInventory.vin == filter_params["vin"])
    
    # Check numeric filters only if they are provided and not equal to -1
    if "year" in filter_params and filter_params["year"] != -1:
        query = query.filter(CarInventory.year >= filter_params["year"])
    if "max_year" in filter_params and filter_params["max_year"] != -1:
        query = query.filter(CarInventory.year <= filter_params["max_year"])
    if "price" in filter_params and filter_params["price"] != -1:
        query = query.filter(CarInventory.price >= filter_params["price"])
    if "max_price" in filter_params and filter_params["max_price"] != -1:
        query = query.filter(CarInventory.price <= filter_params["max_price"])
    if "mileage" in filter_params and filter_params["mileage"] != -1:
        query = query.filter(CarInventory.mileage <= filter_params["mileage"])
    
    results = query.all()
    
    def to_dict(car: CarInventory) -> dict:
        return {
            "stock_number": car.stock_number,
            "vin": car.vin,
            "make": car.make,
            "model": car.model,
            "year": car.year,
            "price": float(car.price),
            "mileage": car.mileage,
            "color": car.color,
            "description": car.description,
            "created_at": car.created_at.isoformat() if car.created_at else None
        }
    
    return [to_dict(c) for c in results]

def generate_conversation_summary(conversation_history: list, conversation_id: str = None) -> dict:
    """
    Generate a summary for a conversation using the OpenAI API.
    
    Args:
        conversation_history (list): List of conversation messages
        conversation_id (str, optional): ID of the conversation
        
    Returns:
        dict: Summary of the conversation
    """
    # Generate a conversation ID if not provided
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
    
    # Prepare the conversation for analysis
    # Filter out system messages and tool messages to focus on the actual conversation
    filtered_history = [
        msg for msg in conversation_history 
        if msg.get("role") in ["user", "assistant"] and 
        not (msg.get("role") == "assistant" and "tool_calls" in msg)
    ]
    
    # Create a prompt for the summary generation
    summary_prompt = {
        "role": "system",
        "content": """
        You are an expert at analyzing car dealership conversations and creating concise, informative summaries.
        
        Analyze the provided conversation and create a summary with the following components:
        
        1. Overall sentiment analysis (positive, neutral, or negative)
        2. Key tags/keywords extracted from the conversation (e.g., 'new model', 'financing', 'trade-in', 'service appointment')
        3. A concise summary of the main discussion points and any relevant customer information
        4. A follow-up routing recommendation (Sales, Service, Management, HR, Finance, or Parts)
        5. Additional insights such as urgency or potential upsell opportunities
        
        Format your response as a JSON object with the following structure:
        {
            "sentiment": "positive/neutral/negative",
            "keywords": ["keyword1", "keyword2", ...],
            "summary": "Concise summary text",
            "department": "Sales/Service/Management/HR/Finance/Parts",
            "insights": {
                "urgency": "high/medium/low",
                "upsell_opportunity": true/false,
                "customer_interest": "high/medium/low",
                "additional_notes": "Any other relevant information"
            }
        }
        
        Be thorough but concise in your analysis.
        """
    }
    
    # Combine the prompt with the conversation history
    messages_for_analysis = [summary_prompt] + filtered_history
    
    # Call the OpenAI API to generate the summary
    try:
        response = client.chat.completions.create(
            model="o3-mini-2025-01-31",
            messages=messages_for_analysis,
            response_format={"type": "json_object"},
            max_completion_tokens=1000,
            reasoning_effort="low"
        )
        
        # Extract the summary from the response
        summary_json = json.loads(response.choices[0].message.content)
        
        # Add the conversation ID to the summary
        summary_json["conversation_id"] = conversation_id
        
        # Calculate token usage and cost
        token_usage = response.usage
        cost_info = calculate_token_cost(
            prompt_tokens=token_usage.prompt_tokens,
            completion_tokens=token_usage.completion_tokens
        )
        
        # Store analytics data for summary generation
        store_request_analytics(token_usage, cost_info, model="o3-mini-2025-01-31")
        
        # Save the summary to the database
        save_summary_to_db(summary_json)
        
        return summary_json
    
    except Exception as e:
        print(f"Error generating conversation summary: {e}")
        # Return a default summary in case of error
        return {
            "conversation_id": conversation_id,
            "sentiment": "neutral",
            "keywords": ["error"],
            "summary": "Error generating summary. Please try again.",
            "department": "Sales",
            "insights": {
                "urgency": "low",
                "upsell_opportunity": False,
                "customer_interest": "unknown",
                "additional_notes": f"Error: {str(e)}"
            }
        }

def save_summary_to_db(summary_data: dict) -> bool:
    """
    Save the conversation summary to the database.
    
    :param summary_data: Dictionary containing the summary information
    :return: True if successful, False otherwise
    """
    try:
        # Create a new interaction record
        new_interaction = AutoLeadInteractionDetails(
            # We don't have a lead_id yet, so it's set to None
            conversation_summary=summary_data["summary"],
            sentiment=summary_data["sentiment"],
            product_keywords=summary_data["keywords"],
            # Set priority_flag based on urgency in insights
            priority_flag=summary_data["insights"].get("urgency") == "high",
            next_steps_recommendation=summary_data["insights"].get("additional_notes", "")
        )
        
        # Add the new interaction to the session
        db.session.add(new_interaction)
        
        # Commit the changes
        db.session.commit()
        return True
    
    except Exception as e:
        print(f"Error saving summary to database: {e}")
        db.session.rollback()
        return False

def get_conversation_summary(conversation_id: str) -> dict:
    """
    Retrieve a conversation summary from the database.
    
    :param conversation_id: The ID of the conversation
    :return: Dictionary containing the summary information or None if not found
    """
    try:
        # Since we're now using AutoLeadInteractionDetails, we need to find the most recent interaction
        # We don't have a direct conversation_id field, so we'll get the most recent interaction
        summary = db.session.query(AutoLeadInteractionDetails).order_by(
            AutoLeadInteractionDetails.created_at.desc()
        ).first()
        
        if summary:
            # Convert the summary to the expected format
            return {
                "conversation_id": conversation_id,  # Use the provided conversation_id
                "sentiment": summary.sentiment,
                "keywords": summary.product_keywords,
                "summary": summary.conversation_summary,
                "department": "Sales",  # Default to Sales since we don't have this field
                "insights": {
                    "urgency": "high" if summary.priority_flag else "medium",
                    "additional_notes": summary.next_steps_recommendation
                },
                "created_at": summary.created_at.isoformat() if summary.created_at else None
            }
        else:
            return None
    
    except Exception as e:
        print(f"Error retrieving summary from database: {e}")
        return None

def detect_end_of_conversation(conversation_history: list) -> bool:
    """
    Analyze the conversation history to detect if the conversation has ended.
    
    This function looks for explicit end-of-conversation signals in the most recent messages.
    
    :param conversation_history: List of message objects in the conversation
    :return: True if the conversation appears to have ended, False otherwise
    """
    # We need at least a few messages to determine if the conversation has ended
    if len(conversation_history) < 3:
        return False
    
    # Get the last few messages (up to 5) to analyze
    recent_messages = conversation_history[-5:]
    
    # Look for end-of-conversation signals in the assistant's messages
    for msg in reversed(recent_messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "").lower()
            
            # Check for explicit end-of-conversation phrases
            end_phrases = [
                "goodbye", "bye", "thank you for chatting", "have a great day",
                "is there anything else", "anything else i can help", "end of conversation",
                "conversation is complete", "conversation has ended", "wrapping up",
                "summarizing our conversation", "conversation summary"
            ]
            
            # Check if any of the end phrases are in the message
            if any(phrase in content for phrase in end_phrases):
                return True
    
    return False

def find_car_review_videos(car_make: str, car_model: str, year: int = None) -> dict:
    """
    Search for car review videos on YouTube based on make, model, and optionally year.
    
    :param car_make: The make of the car (e.g., "Toyota")
    :param car_model: The model of the car (e.g., "Camry")
    :param year: Optional year of the car model
    :return: A dictionary containing video information or error
    """
    try:
        from googleapiclient.discovery import build
        import os
        
        # Get API key from environment variable
        api_key = os.getenv("YOUTUBE_API_KEY")
        print(f"DEBUG: YouTube API Key found: {'Yes' if api_key else 'No'}")
        
        if not api_key:
            print("DEBUG: YouTube API key not configured in environment variables")
            return {"videos": [], "error": "YouTube API key not configured. Please set the YOUTUBE_API_KEY environment variable."}
        
        # Create YouTube API client
        youtube = build('youtube', 'v3', developerKey=api_key)
        
        # Construct search query
        search_query = f"{car_make} {car_model}"
        if year:
            search_query += f" {year}"
        search_query += " review"
        
        print(f"DEBUG: Searching YouTube with query: {search_query}")
        
        # Execute search request
        search_response = youtube.search().list(
            q=search_query,
            part='id,snippet',
            maxResults=5,
            type='video',
            videoCategoryId='28',  # Category ID for "Autos & Vehicles"
            relevanceLanguage='en'
        ).execute()
        
        # Extract video information
        videos = []
        for item in search_response.get('items', []):
            video_id = item['id']['videoId']
            title = item['snippet']['title']
            description = item['snippet']['description']
            thumbnail = item['snippet']['thumbnails']['high']['url']
            
            videos.append({
                'id': video_id,
                'title': title,
                'description': description,
                'thumbnail': thumbnail,
                'url': f"https://www.youtube.com/embed/{video_id}"
            })
        
        print(f"DEBUG: Found {len(videos)} videos for {car_make} {car_model}")
        return {"videos": videos}
    except Exception as e:
        print(f"DEBUG: Error searching for car review videos: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"videos": [], "error": f"Failed to search for car review videos: {str(e)}"}
