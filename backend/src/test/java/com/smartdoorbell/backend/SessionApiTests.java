package com.smartdoorbell.backend;

import com.smartdoorbell.backend.auth.ApiWebConfig;
import com.smartdoorbell.backend.auth.AuthController;
import com.smartdoorbell.backend.event.EventNotFoundException;
import com.smartdoorbell.backend.event.controller.EventController;
import com.smartdoorbell.backend.event.dto.EventDetailResponse;
import com.smartdoorbell.backend.event.service.EventQueryService;
import com.smartdoorbell.backend.event.service.EventService;
import com.smartdoorbell.backend.eventresponse.controller.EventResponseController;
import com.smartdoorbell.backend.feedback.FeedbackController;
import com.smartdoorbell.backend.feedback.FeedbackService;
import com.smartdoorbell.backend.media.controller.MediaController;
import com.smartdoorbell.backend.media.service.MediaService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.time.LocalDateTime;
import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(controllers = {AuthController.class, EventController.class, EventResponseController.class,
        FeedbackController.class, MediaController.class}, properties = "app.auth.password=test-password")
@Import(ApiWebConfig.class)
class SessionApiTests {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private EventService eventService;

    @MockitoBean
    private EventQueryService eventQueryService;

    @MockitoBean
    private FeedbackService feedbackService;

    @MockitoBean
    private MediaService mediaService;

    @Test
    void loginCheckAndLogoutWithTheSameSession() throws Exception {
        when(eventQueryService.listEvents()).thenReturn(List.of());
        mvc.perform(get("/api/v1/auth/check"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.authenticated").value(false));
        MockHttpSession session = login();

        mvc.perform(get("/api/v1/auth/check").session(session))
                .andExpect(status().isOk()).andExpect(jsonPath("$.authenticated").value(true));
        mvc.perform(get("/api/v1/events").session(session))
                .andExpect(status().isOk()).andExpect(content().json("[]"));
        mvc.perform(post("/api/v1/auth/logout").session(session))
                .andExpect(status().isOk()).andExpect(jsonPath("$.authenticated").value(false));
        mvc.perform(get("/api/v1/auth/check"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.authenticated").value(false));
    }

    @Test
    void rejectsWrongPasswordAndEnforcesEventRoutePolicies() throws Exception {
        when(eventQueryService.getEvent(1L)).thenReturn(new EventDetailResponse(
                1L, 1L, "DETECTED", LocalDateTime.of(2026, 1, 1, 12, 0),
                null, null, null, null, null, null, List.of(), null, null, null, List.of()));

        mvc.perform(post("/api/v1/auth/login").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"password\":\"wrong\"}"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/events")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/events/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.eventId").value(1));
        mvc.perform(get("/api/v1/events/1/image")).andExpect(status().isUnauthorized());
        mvc.perform(post("/api/v1/events/1/feedback").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"accuracyLevel\":\"HIGH\"}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void permitsCredentialedPreflightWithoutASession() throws Exception {
        mvc.perform(options("/api/v1/events/1/feedback")
                        .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "content-type"))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, "http://localhost:5173"))
                .andExpect(header().string(HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
    }

    @Test
    void rejectsInvalidFeedbackValues() throws Exception {
        MockHttpSession session = login();
        for (String body : List.of("{}", "{\"accuracyLevel\":\"high\"}", "{\"accuracyLevel\":0}")) {
            mvc.perform(post("/api/v1/events/1/feedback").session(session)
                            .contentType(MediaType.APPLICATION_JSON).content(body))
                    .andExpect(status().isBadRequest());
        }
    }

    @Test
    void visionCanReachBothUploadHandlersWithoutASession() throws Exception {
        when(mediaService.saveImage(eq(1L), any())).thenThrow(new EventNotFoundException(1L));
        when(mediaService.saveRepresentativeImage(eq(1L), any())).thenThrow(new EventNotFoundException(1L));
        MockMultipartFile file = new MockMultipartFile("file", "frame.jpg", "image/jpeg", new byte[]{1});

        mvc.perform(multipart("/api/v1/events/1/image").file(file)).andExpect(status().isNotFound());
        mvc.perform(multipart("/api/v1/events/1/representative-image").file(file)).andExpect(status().isNotFound());
    }

    private MockHttpSession login() throws Exception {
        return (MockHttpSession) mvc.perform(post("/api/v1/auth/login").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"password\":\"test-password\"}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.authenticated").value(true))
                .andReturn().getRequest().getSession(false);
    }
}
