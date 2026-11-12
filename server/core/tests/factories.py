"""Quick fake accounts for tests. Passwords are only hashed when a test asks for one."""

import itertools

from adminusers.models import AdminUser
from companies.models import Company, CompanyUser
from signin import service

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
            "email": f"fake-person{number}@example.test",
            "role": CompanyUser.Role.OWNER,
            **fields,
        }
    )


def make_admin_user(**fields):
    number = next(_numbers)
    return AdminUser.objects.create(
        **{
            "name": f"Fake Admin {number}",
            "email": f"fake-admin{number}@example.test",
            "role": AdminUser.Role.SUPER,
            **fields,
        }
    )


def start_session_for(*, user_id, role, company_id, kind):
    """A session for an account, after making the stored account match what the session says.

    Every request reads the role and company from the account, not from the token, so a
    session for "user 7, an owner of company 3" only works if the account is stored that way.
    """
    if kind == "company":
        Company.objects.get_or_create(
            id=company_id, defaults={"name": f"Fake Company {company_id}"}
        )
        if role == CompanyUser.Role.OWNER:
            # A company has one owner; whoever held it is a member now.
            CompanyUser.objects.filter(company_id=company_id, role="owner").exclude(
                id=user_id
            ).update(role="member")
        CompanyUser.objects.filter(id=user_id).update(company_id=company_id, role=role)
    else:
        AdminUser.objects.filter(id=user_id).update(role=role)
    return service.start_session(user_id=user_id, role=role, company_id=company_id, kind=kind)
