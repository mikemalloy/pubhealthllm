variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "min_capacity" {
  description = "Minimum ACUs (0 enables cluster pause)"
  type        = number
  default     = 0
}

variable "max_capacity" {
  description = "Maximum ACUs"
  type        = number
  default     = 1
}

variable "seconds_until_auto_pause" {
  description = "Idle seconds before cluster pauses (requires min_capacity=0)"
  type        = number
  default     = 300
}
