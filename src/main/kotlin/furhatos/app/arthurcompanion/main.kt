package furhatos.app.arthurcompanion

import furhatos.skills.Skill
import furhatos.flow.kotlin.Flow
import furhatos.app.arthurcompanion.flow.Idle

class ArthurCompanionSkill : Skill() {
    override fun start() {
        Flow().run(Idle)
    }
}

fun main(args: Array<String>) {
    Skill.main(args)
}
