#!/usr/bin/env python3

from login_burner import url_failure, username_matches


assert username_matches("Burner.Name", "burner.name")
assert not username_matches("someone_else", "burner.name")
assert url_failure("https://www.instagram.com/challenge/123/") == "instagram wants a challenge or 2FA"
assert url_failure("https://www.instagram.com/accounts/two_factor/") == "instagram wants a challenge or 2FA"
assert url_failure("https://www.instagram.com/auth_platform/codeentry/?apc=x") == "instagram wants a challenge or 2FA"
assert url_failure("https://www.instagram.com/accounts/login/") is None
