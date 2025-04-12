from models.sql_models import CarInventory
from sqlalchemy import or_

def search_car_inventory(search_query: str, filters: dict, limit: int):
    """
    Search the car_inventory table for records matching the search_query and filters.
    
    Parameters:
      search_query (str): The term to search for across columns.
      filters (dict): Filtering options including keys: make, model, min_price, max_price, and year.
      limit (int): Maximum number of results to return.
      
    Returns:
      A list of matching CarInventory records.
    """
    # Start with the base query.
    query = CarInventory.query

    # Apply filters as provided in the parameters.
    if filters.get("make"):
        query = query.filter(CarInventory.make == filters["make"])
    if filters.get("model"):
        query = query.filter(CarInventory.model == filters["model"])
    if filters.get("min_price") is not None:
        query = query.filter(CarInventory.price >= filters["min_price"])
    if filters.get("max_price") is not None:
        query = query.filter(CarInventory.price <= filters["max_price"])
    if filters.get("year"):
        query = query.filter(CarInventory.year == filters["year"])

    # If a search query is provided, search within key textual columns.
    if search_query:
        like_pattern = f"%{search_query}%"
        query = query.filter(
            or_(
                CarInventory.make.ilike(like_pattern),
                CarInventory.model.ilike(like_pattern),
                CarInventory.description.ilike(like_pattern)
            )
        )

    # Limit the number of results.
    results = query.limit(limit).all()
    return results