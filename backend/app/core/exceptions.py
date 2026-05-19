from fastapi import HTTPException, status


class AFJException(HTTPException):
    pass


class NotFoundError(AFJException):
    def __init__(self, resource: str, id: str = ""):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} não encontrado" + (f": {id}" if id else ""),
        )


class UnauthorizedError(AFJException):
    def __init__(self, detail: str = "Credenciais inválidas"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


class ForbiddenError(AFJException):
    def __init__(self, detail: str = "Acesso não autorizado"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class ValidationError(AFJException):
    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


class ApprovalRequiredError(AFJException):
    def __init__(self, approval_id: str):
        super().__init__(
            status_code=status.HTTP_202_ACCEPTED,
            detail={"message": "Ação aguardando aprovação humana", "approval_id": approval_id},
        )


class AgentError(AFJException):
    def __init__(self, agent: str, detail: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro no agente {agent}: {detail}",
        )
