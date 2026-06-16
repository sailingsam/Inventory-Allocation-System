"""Custom user model: email-based login with a coarse-grained role."""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class Role(models.TextChoices):
    CUSTOMER = "CUSTOMER", "Customer"
    WAREHOUSE_OPERATOR = "WAREHOUSE_OPERATOR", "Warehouse Operator"
    ADMIN = "ADMIN", "Admin"


class UserManager(BaseUserManager):
    """Manager for the email-as-username custom user."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)  # hashes via configured PBKDF2 hasher
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.CUSTOMER)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    # Drop username; email is the unique identifier used to log in.
    username = None
    email = models.EmailField("email address", unique=True)
    role = models.CharField(
        max_length=32, choices=Role.choices, default=Role.CUSTOMER, db_index=True
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # email + password are prompted by createsuperuser automatically

    objects = UserManager()

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.email} ({self.role})"

    # Convenience role predicates used by permission classes.
    @property
    def is_customer(self):
        return self.role == Role.CUSTOMER

    @property
    def is_warehouse_operator(self):
        return self.role == Role.WAREHOUSE_OPERATOR

    @property
    def is_admin_role(self):
        return self.role == Role.ADMIN or self.is_superuser
