"""
Role-Based Access Control (RBAC) implementation.

Implements ISO 27001 A.9.2.3 (Management of privileged access rights)
and A.9.4.1 (Information access restriction).

This module provides fine-grained permission control based on user roles
with support for permission inheritance and delegation.

@module security.rbac
"""

from typing import List, Set, Dict
from enum import Enum

from .models import UserRole, Permission


class RBACManager:
    """
    RBAC manager for permission checking and role management.

    Implements hierarchical role-based access control with
    permission inheritance.

    ISO 27001 Controls:
    - A.9.2.3: Management of privileged access rights
    - A.9.4.1: Information access restriction
    - A.9.2.5: Review of user access rights
    """

    # Role hierarchy (higher roles inherit lower role permissions)
    ROLE_HIERARCHY: Dict[UserRole, int] = {
        UserRole.VIEWER: 1,
        UserRole.TECHNICIAN: 2,
        UserRole.RADIOLOGIST: 3,
        UserRole.ADMIN: 4,
    }

    # Default permissions per role
    ROLE_PERMISSIONS: Dict[UserRole, Set[Permission]] = {
        UserRole.VIEWER: {
            Permission.IMAGE_VIEW,
            Permission.SEGMENTATION_VIEW,
            Permission.SYSTEM_HEALTH,
        },
        UserRole.TECHNICIAN: {
            Permission.IMAGE_VIEW,
            Permission.IMAGE_UPLOAD,
            Permission.SEGMENTATION_VIEW,
            Permission.SEGMENTATION_CREATE,
            Permission.SYSTEM_HEALTH,
        },
        UserRole.RADIOLOGIST: {
            Permission.IMAGE_VIEW,
            Permission.IMAGE_UPLOAD,
            Permission.IMAGE_EXPORT,
            Permission.SEGMENTATION_VIEW,
            Permission.SEGMENTATION_CREATE,
            Permission.SEGMENTATION_DELETE,
            Permission.SYSTEM_HEALTH,
            Permission.AUDIT_VIEW,
        },
        UserRole.ADMIN: {
            # Admin has all permissions
            Permission.IMAGE_VIEW,
            Permission.IMAGE_UPLOAD,
            Permission.IMAGE_DELETE,
            Permission.IMAGE_EXPORT,
            Permission.SEGMENTATION_VIEW,
            Permission.SEGMENTATION_CREATE,
            Permission.SEGMENTATION_DELETE,
            Permission.USER_CREATE,
            Permission.USER_VIEW,
            Permission.USER_UPDATE,
            Permission.USER_DELETE,
            Permission.AUDIT_VIEW,
            Permission.AUDIT_EXPORT,
            Permission.SYSTEM_CONFIG,
            Permission.SYSTEM_HEALTH,
        },
    }

    @classmethod
    def get_permissions_for_role(cls, role: UserRole) -> Set[Permission]:
        """
        Get all permissions for a given role.

        Includes inherited permissions from lower roles in the hierarchy.

        Args:
            role: User role

        Returns:
            Set of permissions

        Example:
            >>> RBACManager.get_permissions_for_role(UserRole.RADIOLOGIST)
            {Permission.IMAGE_VIEW, Permission.IMAGE_UPLOAD, ...}
        """
        permissions = set()

        # Get role level
        role_level = cls.ROLE_HIERARCHY[role]

        # Add permissions from this role and all lower roles
        for r, level in cls.ROLE_HIERARCHY.items():
            if level <= role_level:
                permissions.update(cls.ROLE_PERMISSIONS[r])

        return permissions

    @classmethod
    def has_permission(cls, role: UserRole, permission: Permission) -> bool:
        """
        Check if a role has a specific permission.

        Args:
            role: User role
            permission: Permission to check

        Returns:
            True if role has permission, False otherwise

        Example:
            >>> RBACManager.has_permission(UserRole.VIEWER, Permission.IMAGE_VIEW)
            True
            >>> RBACManager.has_permission(UserRole.VIEWER, Permission.IMAGE_DELETE)
            False
        """
        permissions = cls.get_permissions_for_role(role)
        return permission in permissions

    @classmethod
    def has_any_permission(cls, role: UserRole, permissions: List[Permission]) -> bool:
        """
        Check if a role has any of the specified permissions.

        Args:
            role: User role
            permissions: List of permissions to check

        Returns:
            True if role has at least one permission, False otherwise

        Example:
            >>> RBACManager.has_any_permission(
            ...     UserRole.VIEWER,
            ...     [Permission.IMAGE_VIEW, Permission.IMAGE_DELETE]
            ... )
            True
        """
        role_permissions = cls.get_permissions_for_role(role)
        return any(p in role_permissions for p in permissions)

    @classmethod
    def has_all_permissions(cls, role: UserRole, permissions: List[Permission]) -> bool:
        """
        Check if a role has all of the specified permissions.

        Args:
            role: User role
            permissions: List of permissions to check

        Returns:
            True if role has all permissions, False otherwise

        Example:
            >>> RBACManager.has_all_permissions(
            ...     UserRole.RADIOLOGIST,
            ...     [Permission.IMAGE_VIEW, Permission.IMAGE_EXPORT]
            ... )
            True
        """
        role_permissions = cls.get_permissions_for_role(role)
        return all(p in role_permissions for p in permissions)

    @classmethod
    def is_privileged_role(cls, role: UserRole) -> bool:
        """
        Check if a role is considered privileged (ISO 27001 A.9.2.3).

        Privileged roles: ADMIN, RADIOLOGIST

        Args:
            role: User role

        Returns:
            True if role is privileged, False otherwise
        """
        return role in [UserRole.ADMIN, UserRole.RADIOLOGIST]

    @classmethod
    def can_manage_user(cls, manager_role: UserRole, target_role: UserRole) -> bool:
        """
        Check if a user with manager_role can manage a user with target_role.

        Rule: Can only manage users with equal or lower role level.

        Args:
            manager_role: Role of the manager
            target_role: Role of the target user

        Returns:
            True if manager can manage target, False otherwise

        Example:
            >>> RBACManager.can_manage_user(UserRole.ADMIN, UserRole.VIEWER)
            True
            >>> RBACManager.can_manage_user(UserRole.RADIOLOGIST, UserRole.ADMIN)
            False
        """
        manager_level = cls.ROLE_HIERARCHY[manager_role]
        target_level = cls.ROLE_HIERARCHY[target_role]
        return manager_level >= target_level

    @classmethod
    def get_manageable_roles(cls, role: UserRole) -> List[UserRole]:
        """
        Get list of roles that a user with given role can manage.

        Args:
            role: User role

        Returns:
            List of manageable roles

        Example:
            >>> RBACManager.get_manageable_roles(UserRole.ADMIN)
            [UserRole.VIEWER, UserRole.TECHNICIAN, UserRole.RADIOLOGIST, UserRole.ADMIN]
        """
        manager_level = cls.ROLE_HIERARCHY[role]
        return [
            r for r, level in cls.ROLE_HIERARCHY.items()
            if level <= manager_level
        ]

    @classmethod
    def validate_role_assignment(
        cls,
        assignor_role: UserRole,
        assignee_current_role: UserRole,
        assignee_new_role: UserRole
    ) -> bool:
        """
        Validate if a role assignment/change is allowed.

        Rules:
        1. Assignor must have permission to manage both current and new roles
        2. Cannot elevate privileges beyond assignor's own role

        Args:
            assignor_role: Role of user making the assignment
            assignee_current_role: Current role of user being modified
            assignee_new_role: New role to assign

        Returns:
            True if assignment is valid, False otherwise

        Example:
            >>> RBACManager.validate_role_assignment(
            ...     UserRole.ADMIN,
            ...     UserRole.VIEWER,
            ...     UserRole.RADIOLOGIST
            ... )
            True
            >>> RBACManager.validate_role_assignment(
            ...     UserRole.RADIOLOGIST,
            ...     UserRole.VIEWER,
            ...     UserRole.ADMIN
            ... )
            False
        """
        # Check if assignor can manage both roles
        can_manage_current = cls.can_manage_user(assignor_role, assignee_current_role)
        can_manage_new = cls.can_manage_user(assignor_role, assignee_new_role)

        return can_manage_current and can_manage_new

    @classmethod
    def get_permission_matrix(cls) -> Dict[UserRole, Set[Permission]]:
        """
        Get complete permission matrix for all roles.

        Useful for auditing and documentation (ISO 27001 A.9.2.5).

        Returns:
            Dictionary mapping roles to their permissions

        Example:
            >>> matrix = RBACManager.get_permission_matrix()
            >>> matrix[UserRole.ADMIN]
            {Permission.IMAGE_VIEW, Permission.USER_CREATE, ...}
        """
        return {
            role: cls.get_permissions_for_role(role)
            for role in UserRole
        }

    @classmethod
    def audit_permissions(cls, role: UserRole) -> Dict[str, any]:
        """
        Generate audit report for role permissions (ISO 27001 A.9.2.5).

        Args:
            role: User role

        Returns:
            Audit report with permission details

        Example:
            >>> RBACManager.audit_permissions(UserRole.RADIOLOGIST)
            {
                'role': 'radiologist',
                'role_level': 3,
                'is_privileged': True,
                'permissions_count': 10,
                'permissions': [...],
                'can_manage_roles': [...]
            }
        """
        permissions = cls.get_permissions_for_role(role)

        return {
            "role": role.value,
            "role_level": cls.ROLE_HIERARCHY[role],
            "is_privileged": cls.is_privileged_role(role),
            "permissions_count": len(permissions),
            "permissions": sorted([p.value for p in permissions]),
            "can_manage_roles": [r.value for r in cls.get_manageable_roles(role)],
            "inherited_from": [
                r.value for r, level in cls.ROLE_HIERARCHY.items()
                if level < cls.ROLE_HIERARCHY[role]
            ],
        }


# Singleton instance
rbac_manager = RBACManager()


def check_permission(role: UserRole, permission: Permission) -> bool:
    """
    Convenience function to check permission.

    Args:
        role: User role
        permission: Permission to check

    Returns:
        True if role has permission, False otherwise
    """
    return rbac_manager.has_permission(role, permission)


def get_user_permissions(role: UserRole) -> Set[Permission]:
    """
    Convenience function to get all permissions for a role.

    Args:
        role: User role

    Returns:
        Set of permissions
    """
    return rbac_manager.get_permissions_for_role(role)
