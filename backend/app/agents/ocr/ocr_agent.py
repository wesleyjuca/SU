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

    # Placeholder devolvido quando as libs de OCR não estão instaladas — quem
    # persiste o resultado deve tratá-lo como "indisponível", nunca como texto real.
    UNAVAILABLE: ClassVar[str] = "[OCR não disponível — instale pdfplumber e pytesseract]"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        task = ctx.task_input
        file_path = task.get("file_path")
        file_bytes_b64 = task.get("file_bytes_b64")
        content_type = task.get("content_type")

        if not file_path and not file_bytes_b64:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error="file_path ou file_bytes_b64 obrigatório")

        try:
            texto = await self._extrair_texto(file_path, file_bytes_b64, content_type)
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

    async def _extrair_texto(
        self,
        file_path: str | None,
        file_bytes_b64: str | None,
        content_type: str | None = None,
    ) -> str:
        import asyncio

        is_pdf = bool(
            (content_type and "pdf" in content_type.lower())
            or (file_path and file_path.lower().endswith(".pdf"))
        )

        def _sync_ocr():
            try:
                import pdfplumber
                import pytesseract
                from PIL import Image
                import io

                def _ocr_pdf(source):
                    with pdfplumber.open(source) as pdf:
                        textos = []
                        for page in pdf.pages:
                            txt = page.extract_text()
                            if txt and len(txt.strip()) > 50:
                                textos.append(txt)
                            else:
                                img = page.to_image(resolution=300).original
                                textos.append(pytesseract.image_to_string(img, lang="por"))
                        return "\n\n".join(textos)

                # Caminho por bytes (usado pelo pipeline de upload, que guarda o
                # binário como data URL): PDF vai para pdfplumber via BytesIO,
                # imagem vai direto para o pytesseract.
                if file_bytes_b64:
                    raw = base64.b64decode(file_bytes_b64)
                    if is_pdf:
                        return _ocr_pdf(io.BytesIO(raw))
                    img = Image.open(io.BytesIO(raw))
                    return pytesseract.image_to_string(img, lang="por")

                # Caminho por arquivo em disco (PDF).
                if file_path:
                    return _ocr_pdf(file_path)

                return ""

            except ImportError:
                return self.UNAVAILABLE

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_ocr)

    async def _register_tools(self):
        return []
