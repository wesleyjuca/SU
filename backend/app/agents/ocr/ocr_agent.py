"""ocr_agent — Digitalização e extração de texto de documentos."""
from typing import ClassVar
import base64
from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
import structlog

log = structlog.get_logger()


class OCRAgent(BaseAgent):
    name: ClassVar[str] = "ocr_agent"
    description: ClassVar[str] = "OCR de documentos PDF escaneados via pytesseract"
    requires_human_approval: ClassVar[bool] = False

    async def execute(self, ctx: AgentContext) -> AgentResult:
        task = ctx.task_input
        file_path = task.get("file_path")
        file_bytes_b64 = task.get("file_bytes_b64")

        if not file_path and not file_bytes_b64:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error="file_path ou file_bytes_b64 obrigatório")

        try:
            texto = await self._extrair_texto(file_path, file_bytes_b64)
            return AgentResult(
                status=AgentStatus.SUCCESS,
                agent_name=self.name,
                output={
                    "texto_extraido": texto,
                    "caracteres": len(texto),
                    "palavras": len(texto.split()),
                },
            )
        except Exception as exc:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error=str(exc))

    async def _extrair_texto(self, file_path: str | None, file_bytes_b64: str | None) -> str:
        import asyncio

        def _sync_ocr():
            try:
                import pdfplumber
                import pytesseract
                from PIL import Image
                import io

                if file_path:
                    with pdfplumber.open(file_path) as pdf:
                        textos = []
                        for page in pdf.pages:
                            txt = page.extract_text()
                            if txt and len(txt.strip()) > 50:
                                textos.append(txt)
                            else:
                                img = page.to_image(resolution=300).original
                                txt_ocr = pytesseract.image_to_string(img, lang="por")
                                textos.append(txt_ocr)
                        return "\n\n".join(textos)

                elif file_bytes_b64:
                    raw = base64.b64decode(file_bytes_b64)
                    img = Image.open(io.BytesIO(raw))
                    return pytesseract.image_to_string(img, lang="por")

            except ImportError:
                return "[OCR não disponível — instale pdfplumber e pytesseract]"

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_ocr)

    async def _register_tools(self):
        return []
