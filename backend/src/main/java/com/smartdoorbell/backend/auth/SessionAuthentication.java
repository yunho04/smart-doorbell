package com.smartdoorbell.backend.auth;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

public final class SessionAuthentication {

    private static final String AUTHENTICATED = SessionAuthentication.class.getName();

    private SessionAuthentication() {
    }

    static boolean isAuthenticated(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        return session != null && Boolean.TRUE.equals(session.getAttribute(AUTHENTICATED));
    }

    static void authenticate(HttpServletRequest request) {
        HttpSession session = request.getSession();
        request.changeSessionId();
        session.setAttribute(AUTHENTICATED, true);
    }

    @Target(ElementType.METHOD)
    @Retention(RetentionPolicy.RUNTIME)
    public @interface Required {
    }
}
