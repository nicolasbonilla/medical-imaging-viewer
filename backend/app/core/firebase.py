"""
Firebase Admin SDK initialization and utilities.

Provides Firestore database and Cloud Storage access for the application.
Replaces PostgreSQL for cost optimization while maintaining HIPAA compliance.

@module core.firebase
"""

import os
import logging
from typing import Optional
from functools import lru_cache

import firebase_admin
from firebase_admin import credentials, firestore, storage
from google.cloud.firestore import AsyncClient

logger = logging.getLogger(__name__)

# Global Firebase app instance
_firebase_app: Optional[firebase_admin.App] = None


def get_firebase_app() -> firebase_admin.App:
    """
    Get or initialize the Firebase Admin SDK app.

    Uses Application Default Credentials (ADC) when running in Cloud Run,
    or a service account key file for local development.

    Returns:
        firebase_admin.App: Initialized Firebase app
    """
    global _firebase_app

    if _firebase_app is not None:
        return _firebase_app

    try:
        # Check if already initialized
        _firebase_app = firebase_admin.get_app()
        logger.info("Firebase app already initialized")
        return _firebase_app
    except ValueError:
        # Not initialized yet, proceed with initialization
        pass

    # Try to initialize with credentials
    cred = None

    # Option 1: Service account file (local development)
    service_account_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if service_account_path and os.path.exists(service_account_path):
        cred = credentials.Certificate(service_account_path)
        logger.info(f"Using service account from: {service_account_path}")

    # Option 2: Application Default Credentials (Cloud Run)
    if cred is None:
        cred = credentials.ApplicationDefault()
        logger.info("Using Application Default Credentials")

    # Get project ID
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "medical-imaging-viewer")

    # Initialize Firebase
    _firebase_app = firebase_admin.initialize_app(cred, {
        "projectId": project_id,
        "storageBucket": f"{project_id}.appspot.com"
    })

    logger.info(
        "Firebase Admin SDK initialized",
        extra={"project_id": project_id}
    )

    return _firebase_app


def get_firestore_client() -> firestore.client:
    """
    Get the Firestore client instance.

    Returns:
        Firestore client for database operations
    """
    get_firebase_app()  # Ensure app is initialized
    return firestore.client()


def get_storage_bucket():
    """
    Get the default Cloud Storage bucket.

    Returns:
        Storage bucket for file operations
    """
    get_firebase_app()  # Ensure app is initialized
    return storage.bucket()


# Collection names (consistent with firestore.rules)
class Collections:
    """Firestore collection names."""
    PATIENTS = "patients"
    STUDIES = "studies"
    DOCUMENTS = "documents"
    USERS = "users"
    AUDIT_LOGS = "audit_logs"


# Helper functions for common operations

async def get_document(collection: str, doc_id: str) -> Optional[dict]:
    """
    Get a single document from Firestore.

    Args:
        collection: Collection name
        doc_id: Document ID

    Returns:
        Document data as dict, or None if not found
    """
    db = get_firestore_client()
    doc_ref = db.collection(collection).document(doc_id)
    doc = doc_ref.get()

    if doc.exists:
        data = doc.to_dict()
        data["id"] = doc.id
        return data
    return None


async def create_document(collection: str, data: dict, doc_id: Optional[str] = None) -> str:
    """
    Create a new document in Firestore.

    Args:
        collection: Collection name
        data: Document data
        doc_id: Optional document ID (auto-generated if not provided)

    Returns:
        Created document ID
    """
    db = get_firestore_client()

    if doc_id:
        doc_ref = db.collection(collection).document(doc_id)
        doc_ref.set(data)
        return doc_id
    else:
        doc_ref = db.collection(collection).add(data)
        return doc_ref[1].id


async def update_document(collection: str, doc_id: str, data: dict) -> bool:
    """
    Update an existing document in Firestore.

    Args:
        collection: Collection name
        doc_id: Document ID
        data: Fields to update

    Returns:
        True if successful
    """
    db = get_firestore_client()
    doc_ref = db.collection(collection).document(doc_id)
    doc_ref.update(data)
    return True


async def delete_document(collection: str, doc_id: str) -> bool:
    """
    Delete a document from Firestore.

    Args:
        collection: Collection name
        doc_id: Document ID

    Returns:
        True if successful
    """
    db = get_firestore_client()
    doc_ref = db.collection(collection).document(doc_id)
    doc_ref.delete()
    return True


async def query_collection(
    collection: str,
    filters: Optional[list] = None,
    order_by: Optional[str] = None,
    order_desc: bool = False,
    limit: Optional[int] = None,
    offset: Optional[int] = None
) -> list:
    """
    Query documents from a Firestore collection.

    Args:
        collection: Collection name
        filters: List of (field, operator, value) tuples
        order_by: Field to order by
        order_desc: Order descending if True
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        List of document dicts
    """
    db = get_firestore_client()
    query = db.collection(collection)

    # Apply filters
    if filters:
        for field, op, value in filters:
            query = query.where(field, op, value)

    # Apply ordering
    if order_by:
        direction = firestore.Query.DESCENDING if order_desc else firestore.Query.ASCENDING
        query = query.order_by(order_by, direction=direction)

    # Apply pagination
    if offset:
        # Firestore doesn't support offset directly, need to use cursor pagination
        # For now, fetch extra and slice (not efficient for large offsets)
        if limit:
            query = query.limit(limit + offset)
    elif limit:
        query = query.limit(limit)

    # Execute query
    docs = query.stream()

    results = []
    skip_count = offset or 0
    for doc in docs:
        if skip_count > 0:
            skip_count -= 1
            continue
        data = doc.to_dict()
        data["id"] = doc.id
        results.append(data)

    return results


async def count_collection(collection: str, filters: Optional[list] = None) -> int:
    """
    Count documents in a collection.

    Args:
        collection: Collection name
        filters: Optional filters to apply

    Returns:
        Document count
    """
    db = get_firestore_client()
    query = db.collection(collection)

    if filters:
        for field, op, value in filters:
            query = query.where(field, op, value)

    # Use count aggregation (Firestore native)
    count_query = query.count()
    result = count_query.get()

    return result[0][0].value if result else 0
