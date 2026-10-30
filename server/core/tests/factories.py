"""Quick fake accounts for tests. Passwords are only hashed when a test asks for one."""

import itertools

from adminusers.models import AdminUser
from companies.models import Company, CompanyUser

_numbers = itertools.count(1)


def make_company(**fields):
    number = next(_numbers)
    return Company.objects.create(**{"name": f"Fake Company {number} Ltd", **fields})


def make_company_user(company=None, **fields):
    number = next(_numbers)
    return CompanyUser.objects.create(
        **{
            "company": company or make_company(),
            "name": f"Fake Person {number}",
            "email": f"person{number}@example.test",
            "role": CompanyUser.Role.OWNER,
            **fields,
        }
    )


def make_admin_user(**fields):
    number = next(_numbers)
    return AdminUser.objects.create(
        **{
            "name": f"Fake Admin {number}",
            "email": f"admin{number}@example.test",
            "role": AdminUser.Role.SUPER,
            **fields,
        }
    )
