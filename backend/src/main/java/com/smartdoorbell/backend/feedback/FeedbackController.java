package com.smartdoorbell.backend.feedback;

import com.smartdoorbell.backend.auth.SessionAuthentication;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/events")
public class FeedbackController {

    private final FeedbackService feedbackService;

    public FeedbackController(FeedbackService feedbackService) {
        this.feedbackService = feedbackService;
    }

    @SessionAuthentication.Required
    @PostMapping(path = "/{eventId}/feedback", consumes = MediaType.APPLICATION_JSON_VALUE)
    public FeedbackResponse saveFeedback(@PathVariable Long eventId, @Valid @RequestBody FeedbackRequest request) {
        AccuracyLevel accuracyLevel = AccuracyLevel.valueOf(request.accuracyLevel());
        feedbackService.saveFeedback(eventId, accuracyLevel);
        return new FeedbackResponse(eventId, accuracyLevel);
    }

    public record FeedbackRequest(@NotNull @Pattern(regexp = "HIGH|MEDIUM|LOW") String accuracyLevel) {
    }

    public record FeedbackResponse(Long eventId, AccuracyLevel accuracyLevel) {
    }
}
