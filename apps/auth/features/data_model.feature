Feature: Data model and migrations
    As an operator
    I want the database schema to be described by the models and by a linear migration history
    So that a fresh database and an upgraded database end up with the same tables

    Scenario: Every table of the service is declared by the models
        Given the SQLAlchemy models are imported
        Then the metadata declares 33 tables
        And the metadata declares the tables "users, sessions, oauth2_clients, scopes, tenants, jwks, personal_access_tokens"

    Scenario: Relationships between the models resolve
        Given the SQLAlchemy models are imported
        When the ORM mappers are configured
        Then no mapping error is raised

    Scenario: The schema can be created from the models
        Given the SQLAlchemy models are imported
        When the schema is created on an in-memory SQLite database
        Then 33 tables exist in the database
        And every foreign key points to an existing table

    Scenario: The migration history is a single linear chain
        Given the Alembic migration scripts
        Then the history has exactly one head
        And the history has 33 revisions
        And the head is the revision "060"
        And every revision can be upgraded and downgraded

    Scenario: The migrations create the same tables as the models
        Given the Alembic migration scripts
        And the SQLAlchemy models are imported
        Then the tables created by the migrations are the tables of the models

    Scenario: The migrations only change the schema
        Given the Alembic migration scripts
        Then no migration inserts a row
