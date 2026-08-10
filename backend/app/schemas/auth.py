from pydantic import BaseModel, Field

from app.schemas.user import UserResponse


class GoogleLoginRequest(BaseModel):
    code: str = Field(..., min_length=1, description="Authorization code from Google's consent redirect")
    redirect_uri: str = Field(
        ..., min_length=1, description="Must exactly match the redirect_uri used to obtain the code"
    )


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Seconds until access_token expires")
    user: UserResponse
