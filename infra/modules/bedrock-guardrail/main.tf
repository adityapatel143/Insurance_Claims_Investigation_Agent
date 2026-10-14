resource "aws_bedrock_guardrail" "this" {
  name                      = "${var.name_prefix}-guardrail"
  description               = "Input/output guardrail for the claims investigation assistant."
  blocked_input_messaging   = "This request cannot be processed. It has been routed for analyst review."
  blocked_outputs_messaging = "The generated content was withheld. The case has been routed for analyst review."

  content_policy_config {
    dynamic "filters_config" {
      for_each = {
        SEXUAL     = "HIGH"
        HATE       = "HIGH"
        INSULTS    = "HIGH"
        VIOLENCE   = "MEDIUM"
        MISCONDUCT = "MEDIUM"
      }

      content {
        type            = filters_config.key
        input_strength  = filters_config.value
        output_strength = filters_config.value
      }
    }

    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
  }

  topic_policy_config {
    topics_config {
      name       = "ClaimAdjudication"
      type       = "DENY"
      definition = "Deciding to approve, deny, reject, settle, price, or pay an insurance claim, or determining coverage or eligibility."
      examples = [
        "Approve this claim for payment.",
        "Is this claimant eligible for a payout?",
      ]
    }

    topics_config {
      name       = "MedicalDiagnosis"
      type       = "DENY"
      definition = "Diagnosing, interpreting, or predicting a person's medical or mental health condition."
      examples   = ["What illness does the claimant have based on these notes?"]
    }

    topics_config {
      name       = "ProtectedAttributeInference"
      type       = "DENY"
      definition = "Inferring race, ethnicity, religion, nationality, sexual orientation, disability, age, or gender of a person."
      examples   = ["Guess the claimant's ethnicity from their name."]
    }
  }

  sensitive_information_policy_config {
    dynamic "pii_entities_config" {
      for_each = toset(var.anonymized_pii_types)

      content {
        type           = pii_entities_config.value
        action         = "ANONYMIZE"
        input_action   = "ANONYMIZE"
        output_action  = "ANONYMIZE"
        input_enabled  = true
        output_enabled = true
      }
    }
  }

  word_policy_config {
    managed_word_lists_config {
      type = "PROFANITY"
    }
  }
}

resource "aws_bedrock_guardrail_version" "this" {
  guardrail_arn = aws_bedrock_guardrail.this.guardrail_arn
  description   = var.version_description
}
