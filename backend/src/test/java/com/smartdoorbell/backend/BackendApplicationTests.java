package com.smartdoorbell.backend;

import com.smartdoorbell.backend.device.entity.Device;
import com.smartdoorbell.backend.device.repository.DeviceRepository;
import com.smartdoorbell.backend.event.entity.Event;
import com.smartdoorbell.backend.event.repository.EventRepository;
import com.smartdoorbell.backend.eventresponse.entity.EventResponseHistory;
import com.smartdoorbell.backend.eventresponse.repository.EventResponseHistoryRepository;
import com.smartdoorbell.backend.feedback.FeedbackRepository;
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BackendApplicationTests {

	@Autowired
	private FeedbackRepository feedbackRepository;

	@Autowired
	private DeviceRepository deviceRepository;

	@Autowired
	private EventRepository eventRepository;

	@Autowired
	private EventResponseHistoryRepository eventResponseHistoryRepository;

	@Autowired
	private MockMvc mvc;

	@Autowired
	private EntityManager entityManager;

	@Test
	void contextLoads() {
	}

	@Test
	void feedbackCanBeQueriedByEventId() {
		assertThat(feedbackRepository.findByEventId(Long.MIN_VALUE)).isEmpty();
	}

	@Test
	@Transactional
	void resultReplacesResponseHistoryEvenWhenRetried() throws Exception {
		Device device = deviceRepository.save(new Device("Result test doorbell", "OFFLINE"));
		Event event = eventRepository.save(new Event(device));
		eventResponseHistoryRepository.save(new EventResponseHistory(event, "OLD", "Previous response"));
		String payload = """
				{
				  "riskLevel": "LOW",
				  "summary": "택배 기사가 방문하여 물건을 놓고 떠남",
				  "responses": [
				    {"responseCode": "DELIVERY_01", "responseText": "문 앞에 놓아주세요."},
				    {"responseCode": "THANKS_01", "responseText": "감사합니다."}
				  ]
				}
				""";

		for (int attempt = 0; attempt < 2; attempt++) {
			mvc.perform(post("/api/v1/events/{eventId}/result", event.getId())
							.contentType(MediaType.APPLICATION_JSON).content(payload))
					.andExpect(status().isOk())
					.andExpect(jsonPath("$.status").value("COMPLETED"))
					.andExpect(jsonPath("$.riskLevel").value("LOW"))
					.andExpect(jsonPath("$.summary").value("택배 기사가 방문하여 물건을 놓고 떠남"));
		}

		assertThat(eventResponseHistoryRepository.findAllByEventIdOrderByCreatedAtAscIdAsc(event.getId()))
				.extracting(EventResponseHistory::getResponseCode, EventResponseHistory::getResponseText)
				.containsExactly(tuple("DELIVERY_01", "문 앞에 놓아주세요."), tuple("THANKS_01", "감사합니다."));
	}

	@Test
	@Transactional
	void llmResultStoresAndReturnsConversationWithoutDuplicatesOnRetry() throws Exception {
		Device device = deviceRepository.save(new Device("LLM conversation test doorbell", "OFFLINE"));
		Event event = eventRepository.save(new Event(device));
		Long eventId = event.getId();
		eventResponseHistoryRepository.save(new EventResponseHistory(event, "OLD", "Previous response"));
		String payload = """
				{
				  "riskLevel": "LOW",
				  "summary": "택배 기사가 방문하여 물건을 놓고 떠남",
				  "responseCode": "DELIVERY_01",
				  "responseText": "문 앞에 놓아주세요.",
				  "purpose": "DELIVERY",
				  "conversationSummary": "택배 배송 안내 완료",
				  "conversation": [
				    {
				      "turnNo": 1,
				      "visitorText": "택배입니다.",
				      "purpose": "DELIVERY",
				      "responseCode": "DELIVERY_01",
				      "responseText": "문 앞에 놓아주세요."
				    }
				  ]
				}
				""";

		for (int attempt = 0; attempt < 2; attempt++) {
			mvc.perform(post("/api/v1/events/{eventId}/result", eventId)
							.contentType(MediaType.APPLICATION_JSON).content(payload))
					.andExpect(status().isOk()).andExpect(jsonPath("$.status").value("COMPLETED"));
			entityManager.flush();
			entityManager.clear();

			mvc.perform(get("/api/v1/events/{eventId}", eventId))
					.andExpect(status().isOk())
					.andExpect(jsonPath("$.riskLevel").value("LOW"))
					.andExpect(jsonPath("$.summary").value("택배 기사가 방문하여 물건을 놓고 떠남"))
					.andExpect(jsonPath("$.responseCode").value("DELIVERY_01"))
					.andExpect(jsonPath("$.responseText").value("문 앞에 놓아주세요."))
					.andExpect(jsonPath("$.purpose").value("DELIVERY"))
					.andExpect(jsonPath("$.conversationSummary").value("택배 배송 안내 완료"))
					.andExpect(jsonPath("$.conversation.length()").value(1))
					.andExpect(jsonPath("$.conversation[0].turnNo").value(1))
					.andExpect(jsonPath("$.conversation[0].visitorText").value("택배입니다."))
					.andExpect(jsonPath("$.conversation[0].purpose").value("DELIVERY"))
					.andExpect(jsonPath("$.conversation[0].responseCode").value("DELIVERY_01"))
					.andExpect(jsonPath("$.conversation[0].responseText").value("문 앞에 놓아주세요."))
					.andExpect(jsonPath("$.responses.length()").value(1))
					.andExpect(jsonPath("$.responses[0].responseCode").value("DELIVERY_01"));
		}
	}

	@Test
	@Transactional
	void conversationTakesPrecedenceOverLegacyResponsesIncludingWhenEmpty() throws Exception {
		Device device = deviceRepository.save(new Device("Conversation precedence test doorbell", "OFFLINE"));
		Long eventId = eventRepository.save(new Event(device)).getId();
		String payload = """
				{
				  "conversation": %s,
				  "responses": [{"responseCode": "LEGACY", "responseText": "Legacy response"}]
				}
				""";
		String turns = """
				[
				  {"turnNo": 2, "visitorText": "알겠습니다.", "purpose": "CONFIRMATION",
				   "responseCode": "THANKS_01", "responseText": "감사합니다."},
				  {"turnNo": 1, "visitorText": "택배입니다.", "purpose": "DELIVERY",
				   "responseCode": "DELIVERY_01", "responseText": "문 앞에 놓아주세요."}
				]
				""";

		mvc.perform(post("/api/v1/events/{eventId}/result", eventId)
						.contentType(MediaType.APPLICATION_JSON).content(payload.formatted(turns)))
				.andExpect(status().isOk());
		mvc.perform(get("/api/v1/events/{eventId}", eventId))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.responses.length()").value(2))
				.andExpect(jsonPath("$.conversation.length()").value(2))
				.andExpect(jsonPath("$.conversation[0].turnNo").value(1))
				.andExpect(jsonPath("$.conversation[1].turnNo").value(2))
				.andExpect(jsonPath("$.conversation[1].purpose").value("CONFIRMATION"));

		mvc.perform(post("/api/v1/events/{eventId}/result", eventId)
						.contentType(MediaType.APPLICATION_JSON).content(payload.formatted("[]")))
				.andExpect(status().isOk());
		mvc.perform(get("/api/v1/events/{eventId}", eventId))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.responses").isEmpty())
				.andExpect(jsonPath("$.conversation").isEmpty());
	}

	@Test
	@Transactional
	void legacyResultWithoutHistoryKeepsSavedConversation() throws Exception {
		Device device = deviceRepository.save(new Device("Legacy result test doorbell", "OFFLINE"));
		Long eventId = eventRepository.save(new Event(device)).getId();

		mvc.perform(post("/api/v1/events/{eventId}/result", eventId)
						.contentType(MediaType.APPLICATION_JSON)
						.content("""
								{
								  "purpose": "DELIVERY",
								  "conversationSummary": "택배 배송 안내 완료",
								  "conversation": [
								    {"turnNo": 1, "responseCode": "DELIVERY_01", "responseText": "문 앞에 놓아주세요."}
								  ]
								}
								"""))
				.andExpect(status().isOk());
		mvc.perform(post("/api/v1/events/{eventId}/result", eventId)
						.contentType(MediaType.APPLICATION_JSON)
						.content("""
								{"riskLevel": "LOW", "summary": "배송 완료"}
								"""))
				.andExpect(status().isOk());

		mvc.perform(get("/api/v1/events/{eventId}", eventId))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.summary").value("배송 완료"))
				.andExpect(jsonPath("$.purpose").value("DELIVERY"))
				.andExpect(jsonPath("$.conversationSummary").value("택배 배송 안내 완료"))
				.andExpect(jsonPath("$.conversation[0].responseCode").value("DELIVERY_01"));
	}

}
