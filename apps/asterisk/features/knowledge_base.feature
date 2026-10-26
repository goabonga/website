Feature: Knowledge base with semantic search
    As a phone bot operator
    I want answers stored in PostgreSQL with pgvector
    So that callers get accurate answers from my own content

    The database and the OpenAI embeddings API are replaced by in-memory fakes.

    Scenario: The schema is created on first connection
        Given a fake database without the knowledge_base table
        When the knowledge base connects
        Then the vector extension, the table and the index should have been created

    Scenario: An existing table is left untouched
        Given a fake database that already has the knowledge_base table
        When the knowledge base connects
        Then no schema statement should have been run

    Scenario: Adding an entry stores its embedding
        Given a connected knowledge base
        When I add the entry "What are your hours?" answered "We are open 9am to 5pm"
        Then the database should hold 1 entry
        And the entry should have an embedding

    Scenario: Search returns matching entries above the threshold
        Given a connected knowledge base with the entries:
            | question                    | answer                    |
            | What are your hours?        | We are open 9am to 5pm    |
            | Where are you located?      | We are at 123 Main Street |
            | What services do you offer? | We offer consulting       |
        When I search for "What are your hours?"
        Then the first result should be "What are your hours?"
        And every result should have a similarity of at least 0.7

    Scenario: Search finds nothing when no entry is close enough
        Given a connected knowledge base with the entries:
            | question             | answer                 |
            | What are your hours? | We are open 9am to 5pm |
        When I search for "bananas pyjamas zeppelin"
        Then I should receive no result

    Scenario: Search is limited to the maximum number of results
        Given a connected knowledge base limited to 1 result with the entries:
            | question             | answer                 |
            | What are your hours? | We are open 9am to 5pm |
            | What are your hours? | Open every weekday     |
        When I search for "What are your hours?"
        Then I should receive 1 result

    Scenario: Search without a connection returns nothing
        Given a knowledge base that is not connected
        When I search for "What are your hours?"
        Then I should receive no result

    Scenario: Updating and deleting entries
        Given a connected knowledge base with the entries:
            | question      | answer     |
            | Old question? | Old answer |
        When I update the first entry to "New question?" answered "New answer"
        Then the first entry should read "New question?" answered "New answer"
        When I delete the first entry
        Then the database should hold 0 entries

    Scenario: Sample questions
        Given a connected knowledge base with the entries:
            | question               | answer          |
            | What are your hours?   | 9am to 5pm      |
            | Where are you located? | 123 Main Street |
            | What do you offer?     | Consulting      |
        When I request 2 sample questions
        Then I should receive 2 sample questions

    Scenario: The shared instance exists only when RAG is enabled
        Given RAG is disabled
        Then there should be no shared knowledge base

    Scenario: The shared instance is created once and can be closed
        Given RAG is enabled with a fake database
        When the shared knowledge base is requested twice
        Then both requests should return the same connected instance
        When the shared knowledge base is closed
        Then the database connection should be closed
