package com.smartdoorbell.backend.auth;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {

    private final byte[] password;

    public AuthController(@Value("${app.auth.password}") String password) {
        this.password = password.getBytes(StandardCharsets.UTF_8);
    }

    @PostMapping(path = "/login", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<AuthResponse> login(@RequestBody LoginRequest login, HttpServletRequest request) {
        if (login.password() == null || !MessageDigest.isEqual(password, login.password().getBytes(StandardCharsets.UTF_8))) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(new AuthResponse(false));
        }

        SessionAuthentication.authenticate(request);
        return ResponseEntity.ok(new AuthResponse(true));
    }

    @GetMapping("/check")
    public AuthResponse check(HttpServletRequest request) {
        return new AuthResponse(SessionAuthentication.isAuthenticated(request));
    }

    @PostMapping("/logout")
    public AuthResponse logout(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return new AuthResponse(false);
    }

    public record LoginRequest(String password) {
    }

    public record AuthResponse(boolean authenticated) {
    }
}
