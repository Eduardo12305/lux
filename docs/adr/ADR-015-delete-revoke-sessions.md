## ADR-015: Revogacao de Sessoes ao Deletar Usuario

**Status:** Accepted

**Context:** Admin deleta usuário com sessão ativa — a sessão deve ser invalidada imediatamente.

**Decision:** `UserManagementTool.delete()` chama `session_store.revoke_all(user_id)` antes de deletar o perfil. Voz e senha também são removidos.

**Consequences:** Nenhuma sessão órfã permanece ativa após deleção. In-memory `_revoked` set + DB `is_active = 0` garantem dupla proteção.

**Implementation:** `lux/tools/implementations/user_management.py:_delete_user()`
