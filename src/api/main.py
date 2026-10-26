# src/api/main.py
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.common.logging import get_logger
from src.api.models import QueryRequest, QueryResponse, FeedbackRequest
from src.api.security import verify_api_key
from src.text2sql.agents.graph import run_agentic_text2sql
from src.text2sql.agents.cache_nodes import write_cache_feedback

logger = get_logger(__name__)

app = FastAPI(
    title="TrustSQL API",
    description="Agentic Text2SQL API with Data Quality Awareness",
    version="1.0.0",
)

# Allow frontend (like Streamlit) to communicate with the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "message": "TrustSQL API is running."}


@app.post("/query", response_model=QueryResponse, tags=["Text2SQL"])
def query_database(request: QueryRequest, token: str = Depends(verify_api_key)):
    """
    Main endpoint to translate natural language to SQL, execute it, and return results.
    """
    logger.info(
        f"API received query: '{request.question}' for source: '{request.source_id}'"
    )

    try:
        # Run the LangGraph pipeline
        state = run_agentic_text2sql(
            question=request.question,
            source_id=request.source_id,
            chat_history=request.chat_history,
        )

        # Map the AgentState to our Pydantic Response Model
        return QueryResponse(
            intent=state.get("intent", "unknown"),
            generated_sql=state.get("generated_sql"),
            selected_tables=state.get("selected_tables", []),
            execution_result=state.get("execution_result", []),
            dq_warnings=state.get("dq_warnings", []),
            final_answer=state.get("final_answer", "No answer generated."),
            error_message=state.get("error_message"),
            cache_hit=state.get("cache_hit", False),
        )

    except Exception as e:
        logger.error(f"API Query Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/feedback", tags=["Feedback"])
def submit_feedback(request: FeedbackRequest, token: str = Depends(verify_api_key)):
    """
    Submit feedback for a query. Positive feedback saves it to the Semantic Cache.
    """
    logger.info(
        f"API received feedback ({request.feedback_score}) for query: '{request.question}'"
    )

    if request.feedback_score > 0:
        # Reconstruct a minimal state to pass to the cache writer
        mock_state = {
            "question": request.question,
            "source_id": request.source_id,
            "generated_sql": request.generated_sql,
            "selected_tables": request.tables_used,
            "is_valid_sql": True,
        }
        try:
            cache_id = write_cache_feedback(mock_state, request.feedback_score)
            if cache_id:
                return {
                    "status": "success",
                    "message": "Saved to Semantic Cache",
                    "cache_id": cache_id,
                }
        except Exception as e:
            logger.error(f"Cache write failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to save to cache.")

    return {"status": "success", "message": "Feedback recorded (not cached)."}
