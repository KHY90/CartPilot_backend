"""
LangGraph 시각화 엔드포인트
그래프 구조를 다양한 형식으로 제공
"""
from typing import Literal

from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

router = APIRouter()


class GraphMermaidResponse(BaseModel):
    """Mermaid 다이어그램 응답"""

    format: Literal["mermaid"] = "mermaid"
    diagram: str


class GraphAsciiResponse(BaseModel):
    """ASCII 다이어그램 응답"""

    format: Literal["ascii"] = "ascii"
    diagram: str


@router.get("/graph/mermaid", response_model=GraphMermaidResponse)
async def get_graph_mermaid() -> GraphMermaidResponse:
    """
    LangGraph 그래프를 Mermaid 다이어그램으로 반환

    Returns:
        GraphMermaidResponse: Mermaid 형식 다이어그램
    """
    from app.utils.graph_visualizer import get_graph_mermaid as get_mermaid

    diagram = get_mermaid()
    return GraphMermaidResponse(diagram=diagram)


@router.get("/graph/ascii", response_model=GraphAsciiResponse)
async def get_graph_ascii() -> GraphAsciiResponse:
    """
    LangGraph 그래프를 ASCII 다이어그램으로 반환

    Returns:
        GraphAsciiResponse: ASCII 형식 다이어그램
    """
    from app.utils.graph_visualizer import get_graph_ascii as get_ascii

    diagram = get_ascii()
    return GraphAsciiResponse(diagram=diagram)


@router.get("/graph/png")
async def get_graph_png() -> Response:
    """
    LangGraph 그래프를 PNG 이미지로 반환

    Note:
        이 엔드포인트는 graphviz가 설치되어 있어야 작동합니다.

    Returns:
        PNG 이미지
    """
    from app.agents.orchestrator import build_orchestrator

    orchestrator = build_orchestrator()

    try:
        png_data = orchestrator.get_graph().draw_mermaid_png()
        return Response(content=png_data, media_type="image/png")
    except Exception as e:
        return Response(
            content=f"PNG 생성 실패: {str(e)}",
            status_code=500,
            media_type="text/plain",
        )


@router.get("/graph", response_class=HTMLResponse)
async def get_graph_viewer() -> HTMLResponse:
    """
    LangGraph 그래프를 시각화하는 HTML 뷰어 반환

    브라우저에서 /api/graph 접속시 인터랙티브 다이어그램 표시

    Returns:
        HTML 뷰어
    """
    from app.utils.graph_visualizer import get_graph_mermaid as get_mermaid

    diagram = get_mermaid()

    html_content = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CartPilot LangGraph</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }}
        header {{
            text-align: center;
            margin-bottom: 2rem;
        }}
        h1 {{
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
            background: linear-gradient(90deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .subtitle {{
            color: #a0a0a0;
            font-size: 1.1rem;
        }}
        .graph-container {{
            background: #fff;
            border-radius: 16px;
            padding: 2rem;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        }}
        .mermaid {{
            display: flex;
            justify-content: center;
        }}
        .legend {{
            margin-top: 2rem;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1rem;
        }}
        .legend-item {{
            background: rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            padding: 1rem;
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}
        .legend-icon {{
            width: 40px;
            height: 40px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2rem;
        }}
        .legend-icon.analyze {{ background: #667eea; }}
        .legend-icon.clarify {{ background: #f59e0b; }}
        .legend-icon.route {{ background: #8b5cf6; }}
        .legend-icon.gift {{ background: #ec4899; }}
        .legend-icon.value {{ background: #10b981; }}
        .legend-icon.bundle {{ background: #3b82f6; }}
        .legend-icon.review {{ background: #f97316; }}
        .legend-icon.trend {{ background: #06b6d4; }}
        .legend-text h3 {{
            font-size: 0.9rem;
            margin-bottom: 0.25rem;
        }}
        .legend-text p {{
            font-size: 0.8rem;
            color: #a0a0a0;
        }}
        .actions {{
            margin-top: 2rem;
            display: flex;
            gap: 1rem;
            justify-content: center;
        }}
        .btn {{
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            font-size: 0.9rem;
            font-weight: 500;
            transition: transform 0.2s;
        }}
        .btn:hover {{
            transform: translateY(-2px);
        }}
        .btn-primary {{
            background: linear-gradient(90deg, #667eea, #764ba2);
            color: #fff;
        }}
        .btn-secondary {{
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>CartPilot LangGraph</h1>
            <p class="subtitle">AI Shopping Assistant Agent Flow</p>
        </header>

        <div class="graph-container">
            <div class="mermaid">
{diagram}
            </div>
        </div>

        <div class="legend">
            <div class="legend-item">
                <div class="legend-icon analyze">A</div>
                <div class="legend-text">
                    <h3>analyze_request</h3>
                    <p>사용자 요청 분석 및 의도 분류</p>
                </div>
            </div>
            <div class="legend-item">
                <div class="legend-icon clarify">?</div>
                <div class="legend-text">
                    <h3>clarify</h3>
                    <p>추가 정보 요청 필요시</p>
                </div>
            </div>
            <div class="legend-item">
                <div class="legend-icon route">R</div>
                <div class="legend-text">
                    <h3>route_by_intent</h3>
                    <p>의도별 에이전트 라우팅</p>
                </div>
            </div>
            <div class="legend-item">
                <div class="legend-icon gift">G</div>
                <div class="legend-text">
                    <h3>gift_agent</h3>
                    <p>선물 추천 (GIFT 모드)</p>
                </div>
            </div>
            <div class="legend-item">
                <div class="legend-icon value">V</div>
                <div class="legend-text">
                    <h3>value_agent</h3>
                    <p>가성비 추천 (VALUE 모드)</p>
                </div>
            </div>
            <div class="legend-item">
                <div class="legend-icon bundle">B</div>
                <div class="legend-text">
                    <h3>bundle_agent</h3>
                    <p>묶음 구매 (BUNDLE 모드)</p>
                </div>
            </div>
            <div class="legend-item">
                <div class="legend-icon review">R</div>
                <div class="legend-text">
                    <h3>review_agent</h3>
                    <p>리뷰 분석 (REVIEW 모드)</p>
                </div>
            </div>
            <div class="legend-item">
                <div class="legend-icon trend">T</div>
                <div class="legend-text">
                    <h3>trend_agent</h3>
                    <p>트렌드 추천 (TREND 모드)</p>
                </div>
            </div>
        </div>

        <div class="actions">
            <a href="/api/graph/mermaid" class="btn btn-secondary">Mermaid JSON</a>
            <a href="/api/graph/ascii" class="btn btn-secondary">ASCII</a>
            <a href="/api/graph/png" class="btn btn-primary">PNG 다운로드</a>
        </div>
    </div>

    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
            flowchart: {{
                useMaxWidth: true,
                htmlLabels: true,
                curve: 'basis'
            }}
        }});
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)
