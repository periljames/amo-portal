import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "amodb.main:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        timeout_graceful_shutdown=3,
    )
