from django.db import transaction

from core.errors import AppError

from .models import Company, CompanyUser


@transaction.atomic
def create_company_with_owner(
    *, company_name, country, owner_name, owner_email, password, email_verified=False
):
    """A company never exists without its owner. Sign-up calls this."""
    company = Company.objects.create(name=company_name, country=country)
    owner = CompanyUser(
        company=company,
        name=owner_name,
        email=owner_email,
        role=CompanyUser.Role.OWNER,
        email_verified=email_verified,
    )
    owner.set_password(password)
    owner.save()
    return company, owner


@transaction.atomic
def transfer_ownership(company, new_owner):
    """Hands the company to an active member. Exactly one owner exists before and after."""
    current = CompanyUser.objects.select_for_update().get(company=company, role="owner")
    eligible = (
        new_owner.company_id == company.id
        and new_owner.status == CompanyUser.Status.ACTIVE
        and new_owner.pk != current.pk
    )
    if not eligible:
        raise AppError(
            "owner_transfer_refused",
            "Ownership can only go to another active member of the company.",
            status_code=409,
        )
    # Updates, not saves: a save would refuse to demote the owner. The old owner steps down
    # first because only one owner may exist at any moment.
    CompanyUser.objects.filter(pk=current.pk).update(role=CompanyUser.Role.MEMBER)
    CompanyUser.objects.filter(pk=new_owner.pk).update(role=CompanyUser.Role.OWNER)
