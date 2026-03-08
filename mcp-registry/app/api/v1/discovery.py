"""
Discovery API Endpoints.

Provides intelligent tool discovery and credential management.
"""

import logging
from typing import Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ...services.discovery_service import get_discovery_service, DiscoveryService
from ...db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/discovery", tags=["Discovery"])


# ============================================================================
# Pydantic Models
# ============================================================================

class AnalyzeIntentRequest(BaseModel):
    """Request model for intent analysis."""
    query: str = Field(..., min_length=3, description="User's natural language query")
    organization_id: UUID = Field(..., description="Organization context")
    user_id: UUID = Field(..., description="User making the request")
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional context (create_composition, auto_install, etc.)"
    )


class AnalyzeIntentResponse(BaseModel):
    """Response model for intent analysis."""
    intent: str
    confidence: float
    proposed_composition: Optional[Dict[str, Any]] = None
    requirements: Dict[str, Any]
    setup_actions: list
    credential_setup_url: Optional[str] = None


class CreateSetupLinkRequest(BaseModel):
    """Request model for creating credential setup link."""
    organization_id: UUID
    user_id: UUID
    required_credentials: Dict[str, Any] = Field(
        ...,
        description="Credential requirements in the format: {servers: [...]}"
    )
    proposed_composition: Optional[Dict[str, Any]] = Field(
        None,
        description="Composition structure from /analyze endpoint (will be saved automatically)"
    )
    composition_id: Optional[str] = Field(
        None,
        description="Composition ID (auto-generated if proposed_composition provided)"
    )
    callback_url: Optional[str] = None
    webhook_url: Optional[str] = None
    expires_in_seconds: int = Field(default=3600, ge=300, le=86400)
    metadata: Optional[Dict[str, Any]] = None


class CreateSetupLinkResponse(BaseModel):
    """Response model for credential setup link."""
    token_id: str
    token: str
    setup_url: str
    expires_at: str
    composition_id: Optional[str] = Field(None, description="ID of the created/linked composition")
    qr_code_url: Optional[str] = None


class CompleteSetupRequest(BaseModel):
    """Request model for completing credential setup."""
    credentials: Dict[str, Dict[str, str]] = Field(
        ...,
        description="Credentials by server: {server_id: {cred_name: value}}"
    )
    aliases: Optional[Dict[str, str]] = Field(
        None,
        description="Optional aliases for servers: {server_id: 'alias_name'}"
    )
    test_connection: bool = Field(default=True, description="Test credentials after saving")


class CompleteSetupResponse(BaseModel):
    """Response model for credential setup completion."""
    success: bool
    credentials_saved: list
    composition_ready: bool
    redirect_url: Optional[str] = None
    message: str


# ============================================================================
# Dependencies
# ============================================================================

def get_discovery(db=Depends(get_db)) -> DiscoveryService:
    """Get discovery service instance."""
    # Registry is optional - can be None for now
    return get_discovery_service(db=db, registry=None)


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/analyze", response_model=AnalyzeIntentResponse)
async def analyze_intent(
    request: AnalyzeIntentRequest,
    discovery: DiscoveryService = Depends(get_discovery)
):
    """
    Analyze user intent and discover required tools.

    This is the main entry point for the Discovery System.
    It searches in both installed tools and marketplace,
    classifies requirements, and proposes setup actions.

    **Example**:
    ```json
    {
      "query": "synchroniser mes contacts Notion vers Grist",
      "organization_id": "org-123",
      "user_id": "user-456",
      "context": {
        "create_composition": true
      }
    }
    ```

    **Returns**:
    - Intent classification
    - Proposed composition (if requested)
    - Requirements breakdown (ready/install/credentials)
    - Setup actions in order
    """
    try:
        result = await discovery.analyze_intent(
            query=request.query,
            organization_id=request.organization_id,
            user_id=request.user_id,
            context=request.context
        )

        return AnalyzeIntentResponse(**result)

    except Exception as e:
        logger.error(f"Error analyzing intent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-setup-link", response_model=CreateSetupLinkResponse)
async def create_setup_link(
    request: CreateSetupLinkRequest,
    discovery: DiscoveryService = Depends(get_discovery)
):
    """
    Generate a secure link for credential configuration.

    Used by assistants (Claude, etc.) to create a link that
    users can click to configure their credentials.

    **NEW**: If `proposed_composition` is provided, it will be automatically
    saved as a temporary composition (TTL = expires_in_seconds).
    This ensures the composition exists before credentials are configured.

    **Flow**:
    1. Assistant calls /analyze to get proposed_composition
    2. Calls this endpoint with proposed_composition → **composition is saved**
    3. Returns link to user
    4. User clicks, configures credentials
    5. System updates composition with server_bindings → **composition ready!**

    **Example**:
    ```json
    {
      "organization_id": "org-123",
      "user_id": "user-456",
      "required_credentials": {
        "servers": [...]
      },
      "proposed_composition": {
        "name": "Sync Notion to Grist",
        "description": "...",
        "steps": [...],
        "input_schema": {...}
      },
      "webhook_url": "https://myapp.com/webhook/credential-configured"
    }
    ```
    """
    try:
        composition_id = request.composition_id

        # NEW: If proposed_composition provided, save it first
        if request.proposed_composition and not composition_id:
            from ...orchestration.composition_store import get_composition_store, CompositionInfo
            import uuid

            comp_store = get_composition_store()

            # Generate unique ID if not provided
            composition_id = request.proposed_composition.get("id")
            if not composition_id:
                composition_id = f"comp_{uuid.uuid4().hex[:12]}"

            # Create composition object
            composition = CompositionInfo(
                id=composition_id,
                name=request.proposed_composition.get("name", "Untitled Composition"),
                description=request.proposed_composition.get("description", ""),
                steps=request.proposed_composition.get("steps", []),
                input_schema=request.proposed_composition.get("input_schema", {}),
                output_schema=request.proposed_composition.get("output_schema"),
                server_bindings={},  # Will be filled during complete_setup
                metadata={
                    "organization_id": str(request.organization_id),
                    "user_id": str(request.user_id),
                    "created_via": "discovery",
                    "required_servers": request.proposed_composition.get("required_servers", []),
                    **(request.metadata or {})
                }
            )

            # Save as temporary composition (same TTL as token)
            await comp_store.save_temporary(composition, ttl=request.expires_in_seconds)

            logger.info(
                f"✅ Created temporary composition {composition_id} "
                f"(TTL: {request.expires_in_seconds}s) before setup link"
            )

        # Create token with composition_id (now guaranteed to exist!)
        token = await discovery.create_credential_setup_token(
            user_id=request.user_id,
            organization_id=request.organization_id,
            required_credentials=request.required_credentials,
            composition_id=composition_id,
            callback_url=request.callback_url,
            webhook_url=request.webhook_url,
            expires_in_seconds=request.expires_in_seconds,
            metadata=request.metadata
        )

        return CreateSetupLinkResponse(
            token_id=str(token.id),
            token=token.token,
            setup_url=token.setup_url,
            expires_at=token.expires_at.isoformat(),
            composition_id=composition_id,
            qr_code_url=None  # TODO: Generate QR code
        )

    except Exception as e:
        logger.error(f"Error creating setup link: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/setup/{token}")
async def get_setup_page(
    token: str,
    request: Request,
    discovery: DiscoveryService = Depends(get_discovery)
):
    """
    Display credential configuration page.

    Returns HTML form if accessed from browser,
    or JSON if Accept: application/json header is present.

    **Browser**: Shows interactive form with help links
    **API**: Returns token details and requirements
    """
    try:
        token_obj = await discovery.get_token(token)

        if not token_obj:
            raise HTTPException(status_code=404, detail="Token not found")

        if not token_obj.is_valid:
            if token_obj.is_used:
                raise HTTPException(status_code=410, detail="Token already used")
            else:
                raise HTTPException(status_code=410, detail="Token expired")

        # Check if client wants JSON
        accept_header = request.headers.get("accept", "")
        if "application/json" in accept_header:
            return {
                "token_id": str(token_obj.id),
                "composition_id": token_obj.composition_id,
                "is_valid": token_obj.is_valid,
                "expires_at": token_obj.expires_at.isoformat(),
                "required_credentials": token_obj.required_credentials
            }

        # Return HTML form
        html_content = _generate_setup_html(token_obj)
        return HTMLResponse(content=html_content)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting setup page: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/setup/{token}/complete", response_model=CompleteSetupResponse)
async def complete_setup(
    token: str,
    request: CompleteSetupRequest,
    discovery: DiscoveryService = Depends(get_discovery)
):
    """
    Complete credential configuration.

    Saves credentials and marks token as used.
    Optionally tests connections and triggers webhook.

    **Example**:
    ```json
    {
      "credentials": {
        "notion": {
          "NOTION_API_KEY": "secret_abc123xyz"
        },
        "gmail": {
          "GMAIL_CLIENT_ID": "xxx.apps.googleusercontent.com",
          "GMAIL_CLIENT_SECRET": "secret_yyy"
        }
      },
      "test_connection": true
    }
    ```
    """
    try:
        result = await discovery.complete_credential_setup(
            token_str=token,
            credentials_data=request.credentials,
            aliases=request.aliases or {},
            test_connection=request.test_connection
        )

        return CompleteSetupResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error completing setup: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HTML Generation
# ============================================================================

def _generate_setup_html(token) -> str:
    """Generate HTML form for credential configuration."""
    required_creds = token.required_credentials
    servers = required_creds.get("servers", [])

    # Build form fields HTML
    form_fields = ""
    for server in servers:
        server_id = server.get("server_id", "unknown")
        server_name = server.get("server_name", server_id)
        credentials = server.get("credentials", [])

        form_fields += f"""
        <div class="server-section" data-server="{server_id}">
            <h2>🔗 {server_name}</h2>
            <p class="server-description">{server.get('server_description', '')}</p>

            <div class="credential-field">
                <label for="{server_id}_alias">
                    Name for this instance (optional)
                </label>
                <input
                    type="text"
                    id="{server_id}_alias"
                    name="aliases[{server_id}]"
                    placeholder="E.g.: personal, professional, team..."
                    maxlength="50"
                />
                <p class="help-text">Give a name to easily identify this account</p>
            </div>
        """

        for cred in credentials:
            cred_name = cred.get("name", "")
            cred_description = cred.get("description", "")
            cred_type = cred.get("type", "secret")
            is_required = cred.get("required", True)
            doc_url = cred.get("documentation_url", "")

            input_type = "password" if cred_type in ["secret", "oauth"] else "text"
            required_attr = "required" if is_required else ""

            form_fields += f"""
            <div class="credential-field">
                <label for="{server_id}_{cred_name}">
                    {cred_name}
                    {'<span class="required">*</span>' if is_required else ''}
                </label>
                <input
                    type="{input_type}"
                    id="{server_id}_{cred_name}"
                    name="credentials[{server_id}][{cred_name}]"
                    {required_attr}
                    placeholder="{cred.get('example', '')}"
                />
                <p class="help-text">{cred_description}</p>
                {f'<a href="{doc_url}" target="_blank" class="doc-link">💡 Where to find this?</a>' if doc_url else ''}
            </div>
            """

        form_fields += "</div>"

    html = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Configure your credentials - MCPHub</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
                display: flex;
                align-items: center;
                justify-content: center;
            }}
            .container {{
                background: white;
                border-radius: 12px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                max-width: 600px;
                width: 100%;
                padding: 40px;
            }}
            h1 {{
                color: #333;
                margin-bottom: 10px;
                font-size: 28px;
            }}
            .subtitle {{
                color: #666;
                margin-bottom: 30px;
                font-size: 16px;
            }}
            .server-section {{
                background: #f8f9fa;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 20px;
            }}
            .server-section h2 {{
                color: #495057;
                font-size: 20px;
                margin-bottom: 8px;
            }}
            .server-description {{
                color: #6c757d;
                font-size: 14px;
                margin-bottom: 15px;
            }}
            .credential-field {{
                margin-bottom: 20px;
            }}
            label {{
                display: block;
                color: #495057;
                font-weight: 600;
                margin-bottom: 5px;
                font-size: 14px;
            }}
            .required {{
                color: #dc3545;
            }}
            input {{
                width: 100%;
                padding: 12px;
                border: 2px solid #dee2e6;
                border-radius: 6px;
                font-size: 14px;
                transition: border-color 0.2s;
            }}
            input:focus {{
                outline: none;
                border-color: #667eea;
            }}
            .help-text {{
                font-size: 13px;
                color: #6c757d;
                margin-top: 5px;
            }}
            .doc-link {{
                display: inline-block;
                margin-top: 5px;
                color: #667eea;
                text-decoration: none;
                font-size: 13px;
                font-weight: 600;
            }}
            .doc-link:hover {{
                text-decoration: underline;
            }}
            .buttons {{
                display: flex;
                gap: 10px;
                margin-top: 30px;
            }}
            button {{
                flex: 1;
                padding: 14px;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
            }}
            .btn-primary {{
                background: #667eea;
                color: white;
            }}
            .btn-primary:hover {{
                background: #5568d3;
                transform: translateY(-1px);
            }}
            .btn-secondary {{
                background: #e9ecef;
                color: #495057;
            }}
            .btn-secondary:hover {{
                background: #dee2e6;
            }}
            .footer {{
                text-align: center;
                margin-top: 20px;
                color: #6c757d;
                font-size: 13px;
            }}
            .expires {{
                background: #fff3cd;
                color: #856404;
                padding: 10px;
                border-radius: 6px;
                margin-bottom: 20px;
                font-size: 14px;
            }}
            .loading {{
                display: inline-block;
                width: 14px;
                height: 14px;
                border: 2px solid #fff;
                border-radius: 50%;
                border-top-color: transparent;
                animation: spin 0.6s linear infinite;
            }}
            @keyframes spin {{
                to {{ transform: rotate(360deg); }}
            }}
            .alert {{
                padding: 12px;
                border-radius: 6px;
                margin-bottom: 20px;
                font-size: 14px;
            }}
            .alert-success {{
                background: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }}
            .alert-error {{
                background: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }}
            .field-error {{
                border-color: #dc3545 !important;
            }}
            .error-message {{
                color: #dc3545;
                font-size: 13px;
                margin-top: 5px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 Configuration des identifiants</h1>
            <p class="subtitle">
                {f'For composition "{token.composition_id}"' if token.composition_id else 'Configuration required to continue'}
            </p>

            <div class="expires">
                ⏰ This link expires on {token.expires_at.strftime('%m/%d/%Y at %H:%M')}
            </div>

            <div id="alertContainer"></div>

            <form method="POST" action="/api/v1/discovery/setup/{token.token}/complete" id="setupForm">
                {form_fields}

                <div class="buttons">
                    <button type="button" class="btn-secondary" onclick="testConnection()">
                        Test connection
                    </button>
                    <button type="submit" class="btn-primary">
                        💾 Save
                    </button>
                </div>
            </form>

            <div class="footer">
                🔒 Your credentials are stored securely and encrypted
            </div>
        </div>

        <script>
            function showAlert(message, type = 'error') {{
                const container = document.getElementById('alertContainer');
                const className = type === 'success' ? 'alert-success' : 'alert-error';
                container.innerHTML = `<div class="alert ${{className}}">${{message}}</div>`;
                container.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
            }}

            function clearErrors() {{
                document.querySelectorAll('.field-error').forEach(el => el.classList.remove('field-error'));
                document.querySelectorAll('.error-message').forEach(el => el.remove());
            }}

            function showFieldError(fieldId, message) {{
                const field = document.getElementById(fieldId);
                if (field) {{
                    field.classList.add('field-error');
                    const errorDiv = document.createElement('p');
                    errorDiv.className = 'error-message';
                    errorDiv.textContent = message;
                    field.parentNode.appendChild(errorDiv);
                }}
            }}

            function validateForm() {{
                clearErrors();
                let isValid = true;

                // Validate required fields
                document.querySelectorAll('input[required]').forEach(input => {{
                    if (!input.value.trim()) {{
                        showFieldError(input.id, 'Ce champ est requis');
                        isValid = false;
                    }}
                }});

                return isValid;
            }}

            async function testConnection() {{
                showAlert('Connection test - Feature under development', 'error');
            }}

            document.getElementById('setupForm').addEventListener('submit', async (e) => {{
                e.preventDefault();

                if (!validateForm()) {{
                    showAlert('Please fill in all required fields', 'error');
                    return;
                }}

                const submitBtn = e.target.querySelector('button[type="submit"]');
                const originalText = submitBtn.innerHTML;
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<span class="loading"></span> Saving...';

                const formData = new FormData(e.target);
                const credentials = {{}};
                const aliases = {{}};

                // Parse form data into credentials and aliases objects
                for (let [key, value] of formData.entries()) {{
                    const credMatch = key.match(/credentials\\[([^\\]]+)\\]\\[([^\\]]+)\\]/);
                    const aliasMatch = key.match(/aliases\\[([^\\]]+)\\]/);

                    if (credMatch) {{
                        const [_, server, cred] = credMatch;
                        if (!credentials[server]) credentials[server] = {{}};
                        credentials[server][cred] = value;
                    }} else if (aliasMatch && value.trim()) {{
                        const [_, server] = aliasMatch;
                        aliases[server] = value.trim();
                    }}
                }}

                try {{
                    const payload = {{
                        credentials,
                        test_connection: false
                    }};

                    // Add aliases if any were provided
                    if (Object.keys(aliases).length > 0) {{
                        payload.aliases = aliases;
                    }}

                    const response = await fetch(e.target.action, {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify(payload)
                    }});

                    const result = await response.json();

                    if (response.ok) {{
                        showAlert('✅ ' + (result.message || 'Configuration saved successfully!'), 'success');

                        setTimeout(() => {{
                            if (result.redirect_url) {{
                                window.location.href = result.redirect_url;
                            }} else {{
                                window.location.reload();
                            }}
                        }}, 1500);
                    }} else {{
                        showAlert('❌ ' + (result.detail || 'Error saving configuration'), 'error');
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = originalText;
                    }}
                }} catch (error) {{
                    showAlert('❌ Network error: ' + error.message, 'error');
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalText;
                }}
            }});
        </script>
    </body>
    </html>
    """

    return html
