package com.smartdoorbell.backend;

import com.smartdoorbell.backend.feedback.FeedbackRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class BackendApplicationTests {

	@Autowired
	private FeedbackRepository feedbackRepository;

	@Test
	void contextLoads() {
	}

	@Test
	void feedbackCanBeQueriedByEventId() {
		assertThat(feedbackRepository.findByEventId(Long.MIN_VALUE)).isEmpty();
	}

}
