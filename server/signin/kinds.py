"""The two kinds of sign-in. Each has its own key, audience, roles and cookies."""

COMPANY = "company"
ADMIN = "admin"
KINDS = (COMPANY, ADMIN)

# One fixed signing method; any other (including "none") is rejected when reading a token.
ALGORITHM = "HS256"
ISSUER = "bera"
AUDIENCES = {COMPANY: "bera-company", ADMIN: "bera-admin"}

# Mirrors the roles of the two panels (components/company and components/admin in the web app).
ROLES = {COMPANY: frozenset({"owner", "member"}), ADMIN: frozenset({"super", "support"})}
