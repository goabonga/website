Feature: Amazon SES webhook proxy
  As the webhooks service
  I want to receive Amazon SES notifications via SNS
  So that I can forward them to the internal API

  Scenario: Forward SNS subscription confirmation
    When I send a POST request to "/webhooks/ses" with body
      """
      {
        "Type": "SubscriptionConfirmation",
        "MessageId": "msg-123",
        "TopicArn": "arn:aws:sns:us-east-1:123:topic",
        "SubscribeURL": "https://sns.amazonaws.com/confirm?token=abc"
      }
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Forward SES bounce notification
    When I send a POST request to "/webhooks/ses" with body
      """
      {
        "Type": "Notification",
        "MessageId": "msg-456",
        "TopicArn": "arn:aws:sns:us-east-1:123:topic",
        "Message": "{\"notificationType\":\"Bounce\",\"bounce\":{\"bounceType\":\"Permanent\",\"bounceSubType\":\"General\",\"bouncedRecipients\":[{\"emailAddress\":\"user@example.com\"}],\"timestamp\":\"2024-01-01T00:00:00Z\"},\"mail\":{\"tags\":{}}}"
      }
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Forward SES complaint notification
    When I send a POST request to "/webhooks/ses" with body
      """
      {
        "Type": "Notification",
        "MessageId": "msg-789",
        "TopicArn": "arn:aws:sns:us-east-1:123:topic",
        "Message": "{\"notificationType\":\"Complaint\",\"complaint\":{\"complaintFeedbackType\":\"abuse\",\"complainedRecipients\":[{\"emailAddress\":\"user@example.com\"}],\"timestamp\":\"2024-01-01T00:00:00Z\"},\"mail\":{\"tags\":{}}}"
      }
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Forward SES delivery notification
    When I send a POST request to "/webhooks/ses" with body
      """
      {
        "Type": "Notification",
        "MessageId": "msg-101",
        "TopicArn": "arn:aws:sns:us-east-1:123:topic",
        "Message": "{\"notificationType\":\"Delivery\",\"delivery\":{\"recipients\":[\"user@example.com\"],\"timestamp\":\"2024-01-01T00:00:00Z\",\"smtpResponse\":\"250 OK\"},\"mail\":{\"tags\":{}}}"
      }
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Empty body returns 200
    When I send an empty POST request to "/webhooks/ses"
    Then the response status code should be 200
    And the internal API should not have been called

  Scenario: Forward any payload as raw proxy
    When I send a POST request to "/webhooks/ses" with body
      """
      not valid json
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Forward SNS unsubscribe confirmation
    When I send a POST request to "/webhooks/ses" with body
      """
      {
        "Type": "UnsubscribeConfirmation",
        "MessageId": "msg-unsub",
        "TopicArn": "arn:aws:sns:us-east-1:123:topic"
      }
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Forward SES Configuration Set event
    When I send a POST request to "/webhooks/ses" with body
      """
      {
        "Type": "Notification",
        "MessageId": "msg-cs-1",
        "TopicArn": "arn:aws:sns:us-east-1:123:topic",
        "Message": "{\"eventType\":\"Bounce\",\"bounce\":{\"bounceType\":\"Permanent\",\"bounceSubType\":\"General\",\"bouncedRecipients\":[{\"emailAddress\":\"user@example.com\"}],\"timestamp\":\"2024-01-01T00:00:00Z\"},\"mail\":{\"destination\":[\"user@example.com\"],\"tags\":{}}}"
      }
      """
    Then the response status code should be 200
    And the internal API should have been called

  Scenario: Forward Authorization header when token is configured
    Given the SES internal API token is "ses-secret-token"
    When I send a POST request to "/webhooks/ses" with body
      """
      {"Type": "Notification", "MessageId": "msg-auth"}
      """
    Then the response status code should be 200
    And the internal API should have been called
    And the internal API should have received authorization "Bearer ses-secret-token"

  Scenario: No Authorization header when token is not configured
    When I send a POST request to "/webhooks/ses" with body
      """
      {"Type": "Notification", "MessageId": "msg-noauth"}
      """
    Then the response status code should be 200
    And the internal API should have been called
    And the internal API should not have received authorization

  Scenario: Forward the SNS headers to the internal API
    Given the request has header "x-amz-sns-message-type" with value "Notification"
    And the request has header "x-amz-sns-topic-arn" with value "arn:aws:sns:us-east-1:123:topic"
    When I send a POST request to "/webhooks/ses" with headers and body
      """
      {"Type": "Notification", "MessageId": "msg-headers"}
      """
    Then the response status code should be 200
    And the internal API should have received header "x-amz-sns-message-type" with value "Notification"
    And the internal API should have received header "x-amz-sns-topic-arn" with value "arn:aws:sns:us-east-1:123:topic"

  Scenario: Forward the raw body to the SES internal endpoint
    When I send a POST request to "/webhooks/ses" with body
      """
      {"Type": "Notification", "MessageId": "msg-raw"}
      """
    Then the internal API should have received path "/webhooks/ses"
    And the internal API should have received the request body

  Scenario: Bad gateway when the internal API cannot be reached
    Given the internal API cannot be reached
    When I send a POST request to "/webhooks/ses" with body
      """
      {"Type": "Notification", "MessageId": "msg-down"}
      """
    Then the response status code should be 502

  Scenario: Service unavailable when the internal API is not configured
    Given the SES internal API is not configured
    When I send a POST request to "/webhooks/ses" with body
      """
      {"Type": "Notification", "MessageId": "msg-unconfigured"}
      """
    Then the response status code should be 503
    And the internal API should not have been called
