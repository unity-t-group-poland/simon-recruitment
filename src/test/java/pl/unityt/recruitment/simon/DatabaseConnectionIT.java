package pl.unityt.recruitment.simon;

import org.jooq.DSLContext;
import org.jooq.SQLDialect;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

/** Verifies the starter infrastructure, not the assignment's business rules. */
@ActiveProfiles("test")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DatabaseConnectionIT {

    @Autowired
    private DSLContext dsl;

    @Test
    void connectsToPostgresThroughJooq() {
        assertEquals(SQLDialect.POSTGRES, dsl.dialect());
        assertEquals(Integer.valueOf(1), dsl.selectOne().fetchOne(0, Integer.class));
    }
}
