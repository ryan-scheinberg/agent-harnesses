from app import app


def test_index_returns_hello_world():
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert response.data == b"Hello, World!"
