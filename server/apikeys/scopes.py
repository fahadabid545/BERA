"""What a key may do. Chosen when the key is made and never changed: a different set of scopes
is a new key. There is deliberately no scope for contact details, deleting, downloads, billing,
the team or settings."""

PROJECTS_READ = "projects:read"
CVS_UPLOAD = "cvs:upload"
CANDIDATES_READ = "candidates:read"
SCOPES = (PROJECTS_READ, CVS_UPLOAD, CANDIDATES_READ)
