package com.smartdoorbell.backend.auth;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class ApiWebConfig implements WebMvcConfigurer {

    private final String allowedOrigin;

    public ApiWebConfig(@Value("${app.cors.allowed-origin}") String allowedOrigin) {
        this.allowedOrigin = allowedOrigin;
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/v1/**")
                .allowedOrigins(allowedOrigin)
                .allowedMethods("GET", "HEAD", "POST", "OPTIONS")
                .allowedHeaders(HttpHeaders.CONTENT_TYPE, HttpHeaders.ACCEPT)
                .allowCredentials(true);
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerInterceptor() {

            @Override
            public boolean preHandle(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    Object handler
            ) {

                String uri = request.getRequestURI();

                // AI / Vision 서버가 Event 상세 정보를 조회할 수 있도록
                // GET /api/v1/events/{eventId} 는 세션 인증 없이 허용
                if ("GET".equalsIgnoreCase(request.getMethod())
                        && uri.matches("^/api/v1/events/\\d+$")) {
                    return true;
                }

                if (handler instanceof HandlerMethod method
                        && method.hasMethodAnnotation(SessionAuthentication.Required.class)) {

                    response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");

                    if (!SessionAuthentication.isAuthenticated(request)) {
                        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                        return false;
                    }
                }

                return true;
            }

        }).addPathPatterns("/api/v1/events/**");
    }
}